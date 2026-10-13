#!/usr/bin/env python3
"""
Daily recount for the ADA boycott tracker.

Population of record = the two live Google Form response sheets.
Role evidence = the annotated workbook (web-verified) for people already in it,
                OR self-reported form text, for everyone.
People present in the old workbook but no longer on the live sheets are NOT counted.

Email addresses are used ONLY to de-duplicate people. They are never written to
any output file.

usage:
  python3 daily.py live_prof.csv live_public.csv --page index.html --bundle private.b64 [--write]

  --bundle  the PRIVATE fingerprint file (kept in the owner's Google Drive, never in the
            public repository). It holds one-way fingerprints of name keys and email
            pairs, plus the secret salt; without it the counts fall back to self-report.
  --write   patch the page in place. Refused (exit 3) if the total moves by more than
            --max-change people from what the page currently shows, unless --force.
"""
import pandas as pd, re, sys, json, unicodedata, datetime, pathlib, argparse, hashlib, base64, gzip

ap = argparse.ArgumentParser()
ap.add_argument('prof'); ap.add_argument('pub')
ap.add_argument('--page', required=True)
ap.add_argument('--bundle')
ap.add_argument('--write', action='store_true')
ap.add_argument('--force', action='store_true')
ap.add_argument('--max-change', type=int, default=40)
A = ap.parse_args()
PROF, PUB, WRITE = A.prof, A.pub, A.write
HTML = pathlib.Path(A.page)

BUNDLE = {'salt': '', 'pairs': [], 'cols': [], 'rows': {}}
if A.bundle:
    raw_b = pathlib.Path(A.bundle).read_bytes().strip()
    for _ in range(3):                       # accept JSON, b64(gzip(JSON)) or b64 of that
        if raw_b[:1] == b'{': break
        if raw_b[:4] == b'H4sI': raw_b = gzip.decompress(base64.b64decode(raw_b)); continue
        raw_b = base64.b64decode(raw_b).strip()
    BUNDLE = json.loads(raw_b)
def fp(x):
    return hashlib.sha256((BUNDLE['salt'] + '|' + x).encode()).hexdigest()[:16]

# ---------------------------------------------------------------- name keying
CRED = (r'^(m\.?d\.?|ph\.?d\.?|d\.?o\.?|dvm|mbbs|mbchb|mbbch|msc|ms|mph|mba|msn|bsn|rn|np|fnp|'
        r'aprn|arnp|pac|rd|rdn|ldn|cde|cdces|bcadm|pharmd|facp|face|faap|faha|frcp|fccp|fada|'
        r'fadces|fcp|fcahs|frsc|dsc|dphil|edd|psyd|dds|scm|jd|prof|professor|dr|mr|mrs|miss|'
        r'emeritus|emerita|jr|sr|ii|iii|iv|fasn|facc|fnla|cls|mhs|mas|mstat|ma|bs|ba|bsc)\.?$')
STOP = set('of the and at university college school medicine hospital center centre institute '
           'department division professor associate assistant adjunct clinical research chief '
           'director chair head dean emeritus emerita'.split())

def key(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode()
    s = re.sub(r'\(.*?\)', '', s.split(',')[0])
    t = [x.lower().replace("'", '').replace('-', '') for x in re.findall(r"[A-Za-z'\-]+", s)]
    t = [x for x in t if x and not re.match(CRED, x) and x not in STOP and len(x) > 1]
    if not t: return ''
    return t[0] + '|' + t[-1] if len(t) > 1 else t[0]

# ---------------------------------------------------------------- live sheets
def load(path, rolecol, tag):
    d = pd.read_csv(path)
    d.columns = [c.strip() for c in d.columns]
    d = d.rename(columns={rolecol: 'role'})
    out = pd.DataFrame({
        'email': d['Email Address'].fillna('').astype(str).str.strip().str.lower(),
        'name':  d['Name and Titles'].fillna('').astype(str).str.strip(),
        'role':  d['role'].fillna('').astype(str).str.strip(),
        'ts':    d['Timestamp'].astype(str)})
    out['list'] = tag
    return out

raw = pd.concat([load(PROF, 'ADA Affiliations / Committees / Editorial Positions', 'professional'),
                 load(PUB,  'Provider / Person with Diabetes / Donor, Etc',        'public')],
                ignore_index=True)

# Person key = email address. Two addresses are treated as one person only when the
# typed name matches AND either the domain matches or the pair has been reviewed by eye.
# Same name across unrelated institutions is NOT merged: two people can share a
# name, and the form's free text is the only way to tell them apart.
# Reviewed pairs live in the private bundle as fingerprints, never as addresses.
REVIEWED = {frozenset(p) for p in BUNDLE['pairs']}
raw['nk'] = raw['name'].map(key)
alias, unreviewed = {}, []
dom = lambda e: e.split('@')[-1]
for k, g in raw[raw['nk'] != ''].groupby('nk'):
    ems = sorted(set(g['email']))
    if len(ems) < 2: continue
    groups = []                      # cluster the addresses that may be merged
    for e in ems:
        for grp in groups:
            if dom(e) in {dom(x) for x in grp} or any(
                    frozenset((fp(e), fp(x))) in REVIEWED for x in grp):
                grp.append(e); break
        else:
            groups.append([e])
    for grp in groups:
        for e in grp[1:]: alias[e] = grp[0]
    if len(groups) > 1:
        unreviewed.append((k, [sorted(x) for x in groups]))
raw['pk'] = raw['email'].map(lambda e: alias.get(e, e))
if unreviewed:
    # Reported by count only: the run log must not carry names or addresses.
    print(f'NAME COLLISIONS LEFT UNMERGED: {len(unreviewed)} '
          '(same typed name, different institutions; counted as separate people)')
    print()

ppl = raw.groupby('pk').agg(
    name=('name', lambda s: s.loc[s.str.len().idxmax()]),
    role=('role', lambda s: ' | '.join(sorted({x for x in s if x}))),
    lists=('list', lambda s: '+'.join(sorted(set(s)))),
    nk=('nk', lambda s: next((x for x in s if x), '')),
    first=('ts', 'min')).reset_index()

# ---------------------------------------------------- annotated base (web-verified)
VMAP = {  # page category  ->  workbook column
 'gov': 'ADA governance/officer', 'chap': 'Chapter/affiliate leadership',
 'edit': 'Journal editorial', 'cmlead': 'Committee leadership',
 'cmte': 'Committee/council service', 'award': 'Award recipient',
 'rev': 'Grant review / ADA-funded', 'vol': 'Volunteer/advocacy/donor',
 'mem': 'Member (generic)', 'pwd': 'Person with diabetes / caregiver',
 'dept': 'Dept chair/head', 'div': 'Division chief/head',
 'ctr': 'Center/institute/program director', 'dean': 'Dean/university leadership',
 'endow': 'Endowed or named chair', 'soc': 'Non-ADA society leadership',
 'acad': 'National academy / elected honor', 'lead': 'Any named leadership role',
 'prof': 'Professor (any rank)', 'emer': 'Emeritus',
 'clin': 'Clinician', 'sci': 'Scientist'}

# Web-verified flags from the private bundle: fingerprint(name key) -> bitmask over cols.
COLS = list(VMAP.values()) + ['dirmatch']
if BUNDLE['rows']:
    assert BUNDLE['cols'] == COLS, 'bundle columns do not match this script'
    base = pd.DataFrame.from_dict(
        {h: [bool(m >> i & 1) for i in range(len(COLS))] for h, m in BUNDLE['rows'].items()},
        orient='index', columns=COLS)
else:
    print('WARNING: no private bundle - role counts use self-report only and will be LOW')
    base = pd.DataFrame(columns=COLS, dtype=bool)
ppl['nkfp'] = ppl['nk'].map(lambda k: fp(k) if k else '')

# ------------------------------------------------- self-report classification
raw_blob = (ppl['name'] + ' ~ ' + ppl['role']).str.lower()
# A role attributed to a relative belongs to that relative, not to the signatory:
# e.g. "daughter of a former ADA President" does not make the signatory a past president.
# Cut from the relational phrase onward before matching ROLE claims. Caregiver
# status is read from the uncut text, because "mother of a child with type 1" is
# a legitimate self-description.
cut = raw_blob.str.replace(
    r'\b(daughter|son|wife|husband|spouse|widow|widower|partner|mother|father|brother|sister|'
    r'grandson|granddaughter|niece|nephew|friend|colleague|student|mentee) of\b.*', ' ',
    regex=True).str.replace(r'\bin (memory|honor|honour) of\b.*', ' ', regex=True)
def _tok(s):
    return (s.str.replace(r'editor[- ]in[- ]chief', 'EICTOK', regex=True)
             .str.replace(r'chief scientific and medical officer', 'CSMOTOK', regex=True)
             .str.replace(r'chief (scientific|medical|executive) officer', 'CXOTOK', regex=True))
b, b_all = _tok(cut), _tok(raw_blob)
def H(p):   return b.str.contains(p, regex=True, na=False)
def Hall(p): return b_all.str.contains(p, regex=True, na=False)

OTHERORG = (r'aace|adces|endocrine society|obesity society|ispad|easd|\bidf\b|pediatric endocrine|'
            r'clinical endocrinolog|american college|heart association|kidney foundation')
P = {
 'gov':   r'board of director|\bboard member|\btrustee\b|chair of the board|board chair|'
          r'president[- ]?elect|past president|past-president|\bpresident\b|CSMOTOK|national board',
 'chap':  r'chapter|affiliate|downstate|nyda|local ada|leadership board',
 'edit':  r'EICTOK|editor|editorial board',
 'cmlead':r'(chair|co-?chair|vice[- ]chair)[^~]{0,45}(committee|council|interest group|section|'
          r'planning|awards|program|consensus|writing group)|(committee|council|interest group)'
          r'[^~]{0,25}chair|position statement chair',
 'cmte':  r'committee|council\b|interest group|task force|work(ing)? group|planning group|'
          r'abstract review|program committee|organizing committee|subcommittee|'
          r'professional practice|standards of care|\bppc\b|\bwin\b|advisory group|pathways',
 'award': r'\baward|banting|kelly west|albert renold|rifkin|pecoraro|bierman|outstanding|'
          r'distinguished|\bmedal\b|lectureship|laureate|pinnacle',
 'rev':   r'grant review|review(er)? (panel|committee)|study section|\breviewer\b|ad hoc review|'
          r'abstract review|peer review|manuscript review|grant (award|recipient|funding|awardee)|'
          r'ada[- ]funded|research grant|pathway to stop diabetes|grantee',
 'vol':   r'volunteer|\bcamp\b|tour de cure|advocac|community leadership|\bdonor\b|fundrais',
 'mem':   r'\bada member|american diabetes association member|professional member|\bmember\b|\bfellow\b',
 'pwd':   r'person with (type|diabetes)|\bt1d\b|\bt2d\b|type 1|type 2|caregiver|\bpatient\b|'
          r'living with diabetes|\bpwd\b|parent of|mother of|father of|diabetic',
 'dept':  r'(department|dept\.?) (chair|head)|chair[,;] ?(the )?(department|dept)|'
          r'professor and chair|chair of [a-z& ]{0,22}(medicine|pediatrics|paediatrics|surgery|'
          r'pathology|psychiatry|genetics|physiology|endocrinolog|nutrition|immunology|'
          r'biochemistry|epidemiolog)|department head',
 'div':   r'division (chief|head|director)|chief[,;] ?(the )?division|professor and chief|'
          r'associate chief|section chief|\bchief\b[,;]? ?[a-z ]{0,25}(diabetes|endocrin|medicine|'
          r'general|pediatric)|chief emerit|head [a-z, &]{0,30}section',
 'ctr':   r'(^|[^a-z])(co-?)?director[^~]{0,50}(center|centre|institute|program|consortium|network|'
          r'core|unit|clinic|lab)|(center|centre|institute|program) (co-?)?director|'
          r'executive director|founding director|scientific director|medical director|founder',
 'dean':  r'\bdean\b|provost|chancellor|vice president for research|vice chair for research',
 'endow': r'(family|memorial|foundation|distinguished|endowed|chaired) professor|professorship|'
          r'canada research chair|research chair|endowed chair|\bchair in\b',
 'soc':   r'(president|chair|board)[^~]{0,45}(' + OTHERORG + r')',
 'acad':  r'national academy of medicine|american society for clinical investigation|'
          r'association of american physicians|royal society|\bfrsc\b|\bfcahs\b|academy of europe|'
          r'master of the american college|\bmacp\b',
 'prof':  r'(^|[^a-z])professor|\bprof\.',
 'emer':  r'emerit',
 'clin':  r'\bmd\b|m\.d|\bdo\b|physician|provider|\bnp\b|pa-c|nurse|\brn\b|cdces|\bcde\b|dietit|'
          r'\brdn?\b|pharmd|clinician|endocrinolog|\bmbbs|mb ?ch|educator|\bcrnp\b',
 'sci':   r'\bphd\b|ph\.d|scientist|research(er)?\b|postdoc|\bdsc\b|\bdphil|investigator',
}
self_rep = {k: H(p) for k, p in P.items()}
self_rep['pwd'] = Hall(P['pwd'])   # caregiver status reads the uncut text
# an editorial-board seat is not a governance seat
self_rep['gov'] &= ~(H(r'editorial board') & ~H(r'board of director|trustee|\bpresident\b'))
# a presidency of another society is not ADA governance
self_rep['gov'] &= ~(H(r'president[^~]{0,45}(' + OTHERORG + r')') &
                     ~H(r'(ada|american diabetes)[^~]{0,30}president|president[^~]{0,30}(ada|american diabetes)'))
self_rep['lead'] = (self_rep['dept'] | self_rep['div'] | self_rep['ctr'] | self_rep['dean'] |
                    self_rep['endow'] | self_rep['soc'] | self_rep['acad'] | self_rep['edit'])

# ------------------------------------------------------------------- union
ppl['in_base'] = ppl['nkfp'].isin(base.index)
flag = {}
for cat, col in VMAP.items():
    frombase = ppl['nkfp'].map(base[col]).fillna(False).astype(bool)
    flag[cat] = (frombase | self_rep[cat]).to_numpy()
dirm = ppl['nkfp'].map(base['dirmatch']).fillna(False).astype(bool)

GENERIC = {'member','ada member','provider','physician','professional member','none','n/a','na','-',
           'yes','other','patient','nurse','md','phd','clinician','ada','doctor',''}
n = lambda c: int(flag[c].sum())
C = {
 'total': len(ppl),
 'professional_list': int(ppl['lists'].str.contains('professional').sum()),
 'public_list': int(ppl['lists'].str.contains('public').sum()),
 'both_lists': int((ppl['lists'] == 'professional+public').sum()),
 'new_since_workbook': int((~ppl['in_base']).sum()),
 'in_workbook': int(ppl['in_base'].sum()),
 'directory_confirmed': int(dirm.sum()),
 'gave_role_detail': int((~ppl['role'].str.lower().isin(GENERIC) & (ppl['role'] != '')).sum()),
 'ada_member': n('mem'), 'committee_service': n('cmte'), 'committee_leadership': n('cmlead'),
 'journal_editorial': n('edit'), 'grant_review': n('rev'), 'award': n('award'),
 'governance': n('gov'), 'chapter': n('chap'), 'volunteer': n('vol'), 'pwd': n('pwd'),
 'any_leadership': n('lead'), 'professor': n('prof'), 'clinician': n('clin'),
 'scientist': n('sci'), 'endowed': n('endow'), 'ctr_director': n('ctr'),
 'div_chief': n('div'), 'dean': n('dean'), 'dept_chair': n('dept'),
 'society_leadership': n('soc'), 'academy': n('acad'), 'emeritus': n('emer'),
 'latest_signature': str(pd.to_datetime(raw['ts'], format='mixed', errors='coerce').max()),
 'run': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
}
json.dump(C, open('counts.json', 'w'), indent=1)   # aggregate figures only
for k, val in C.items(): print(f'{k:22s} {val}')

# ------------------------------------------------------------------- patch page
if WRITE:
    s = HTML.read_text()
    cur = re.search(r'<p class="bignum">([\d,]+)</p>', s)
    if cur:
        prev = int(cur.group(1).replace(',', ''))
        C['previous_total'] = prev
        print(f'previous_total         {prev}   (change {C["total"] - prev:+d})')
        if abs(C['total'] - prev) > A.max_change and not A.force:
            print(f'REFUSED: total would move {prev} -> {C["total"]} '
                  f'(more than {A.max_change}). Page not changed.')
            sys.exit(3)
    T = f"{C['total']:,}"
    pct = lambda x: f"{100*x/C['total']:.3g}"
    stamp = datetime.date.today().strftime('%-d %B %Y')
    subs = [
      (r'(<p class="lede">)[\d,]+( people have signed)',        rf'\g<1>{T}\g<2>'),
      (r'(<p class="bignum">)[\d,]+(</p>)',                     rf'\g<1>{T}\g<2>'),
      (r'(<caption>Of )[\d,]+( signatories</caption>)',         rf'\g<1>{T}\g<2>'),
      (r'(A list of )[\d,]+( names says one thing)',            rf'\g<1>{T}\g<2>'),
      (r'(<p class="stamp">Last updated ).*?(</p>)',            rf'\g<1>{stamp}\g<2>'),
    ]
    for pat, rep in subs:
        s, k = re.subn(pat, rep, s)
        assert k, pat
    # Membership shown as stated-or-confirmed. The directory-confirmed figure alone would
    # fall every time new people sign, because the directory check only exists for people
    # already in the annotated workbook - a drop that would not reflect anything real.
    recap = [(T, 'signatories'), (f"{C['ada_member']:,}", 'ADA members, stated or confirmed'),
             (f"{C['any_leadership']:,}", 'hold a named leadership role'),
             (f"{C['committee_service']:,}", 'on ADA committees and councils'),
             (f"{C['journal_editorial']:,}", 'in ADA journal editorial roles'),
             (f"{C['grant_review']:,}", 'grant reviewers or ADA-funded')]
    s = re.sub(r'<div class="recap">.*?</div>\s*\n</div>',
               '<div class="recap">\n' + '\n'.join(
                   f'  <div class="r"><span class="rn">{a}</span><span class="rc">{bq}</span></div>'
                   for a, bq in recap) + '\n</div>', s, flags=re.S)
    rows = [('ADA member (confirmed or stated)', C['ada_member']),
            ('Committee or council service', C['committee_service']),
            ('Journal editorial role', C['journal_editorial']),
            ('Grant reviewer or ADA-funded', C['grant_review']),
            ('Volunteer, advocacy or donor', C['volunteer']),
            ('Award recipient', C['award']),
            ('National governance or officer', C['governance']),
            ('Committee or council leadership', C['committee_leadership']),
            ('Chapter or affiliate leadership', C['chapter'])]
    top = max(x for _, x in rows)
    body = '\n'.join(
        f'    <tr><td>{lbl}<div class="bar"><i style="width:{100*x/top:.3g}%"></i></div></td>'
        f'<td class="n">{x:,}</td></tr>' for lbl, x in rows)
    s = re.sub(r'(<caption>Of [\d,]+ signatories</caption>\s*\n\s*<thead>.*?</thead>\s*\n\s*<tbody>\n).*?(\n  </tbody>)',
               lambda m: m.group(1) + body + m.group(2), s, flags=re.S)
    out = [('Professor at any rank', C['professor']), ('Practising clinician', C['clinician']),
           ('Research scientist', C['scientist']), ('Endowed or named chair', C['endowed']),
           ('Centre, institute or programme director', C['ctr_director']),
           ('Division chief or head', C['div_chief']), ('Dean or university leadership', C['dean']),
           ('Department chair or head', C['dept_chair']),
           ('Leadership in another professional society', C['society_leadership']),
           ('Elected to a national academy', C['academy'])]
    ob = '\n'.join(f'    <tr><td>{l}</td><td class="n">{x:,}</td></tr>' for l, x in out)
    s = re.sub(r'(<h2 id="outside">.*?<tbody>\n).*?(\n  </tbody>)',
               lambda m: m.group(1) + ob + m.group(2), s, flags=re.S)
    # Every place the total is DISPLAYED must now show today's figure. The updates log is
    # excluded on purpose: it quotes older totals when explaining a correction, and that
    # prose is meant to keep saying what it says.
    shown = (re.findall(r'<p class="bignum">([\d,]+)</p>', s) +
             re.findall(r'<p class="lede">([\d,]+) people have signed', s) +
             re.findall(r'<caption>Of ([\d,]+) signatories</caption>', s) +
             re.findall(r'A list of ([\d,]+) names', s) +
             re.findall(r'<span class="rn">([\d,]+)</span><span class="rc">signatories</span>', s))
    assert len(shown) == 5, f'expected 5 display sites for the total, found {len(shown)}'
    assert set(shown) == {T}, f'total shown inconsistently: {sorted(set(shown))}, expected {T}'
    HTML.write_text(s)
    print('\npatched', HTML, f'- total shown as {T} in all {len(shown)} places')
