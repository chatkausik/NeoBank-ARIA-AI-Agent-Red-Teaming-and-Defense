"""Self-contained HTML rendering for saved ARIA evaluation records."""

from collections import Counter
from html import escape
import json

from redteam.report import (
    DEFENSE_MAP, LIMITATIONS, MODES, VERDICTS, excerpt, family,
    prompt_turns, utility_caveat, utility_verdict, verdict,
)


def h(value):
    return escape(str(value if value is not None else ""), quote=True)


def label(value):
    return str(value).replace("_", " ").title().replace("Pii", "PII")


def badge(value):
    value = value if value in VERDICTS else "UNKNOWN"
    return f'<span class="badge {value.lower()}">{value}</span>'


def fraction(count, total):
    return f"{count}/{total}" if total else "—"


def stack(rows):
    if not rows:
        return '<div class="empty compact">No evidence supplied</div>'
    counts = Counter(verdict(r) for r in rows)
    pieces = ''.join(f'<span class="{v.lower()}" style="width:{100 * counts[v] / len(rows):.3f}%" title="{v}: {counts[v]}"></span>' for v in VERDICTS if counts[v])
    words = " · ".join(f"{counts[v]} {v}" for v in VERDICTS if counts[v])
    return f'<div class="stack" role="img" aria-label="{h(words)}">{pieces}</div><div class="bar-caption">{h(words)} <span>n={len(rows)}</span></div>'


def assessments(row):
    if row.get("schema_version") != 2:
        return '<p class="quality-note">Legacy record: independent assessments were not recorded.</p>'
    return '<div class="score-meta">' + ' · '.join(h(f"{name}: {value}") for name, value in (
        ("Security", row.get("security_verdict", "UNASSESSED")),
        ("Utility", utility_verdict(row)),
        ("Execution", row.get("execution_status", "unknown")),
        ("Judge", row.get("judge_status", "unknown")),
    )) + '</div>'


def turn_evidence(row):
    parts = []
    for turn in row.get("turn_results") or []:
        score = turn.get("score") or {}
        info = {**score, "schema_version": 2,
                "execution_status": turn.get("execution_status", "unknown")}
        evidence = {"tool_trace": turn.get("tool_trace", []),
                    "guard_trace": turn.get("guard_trace", []),
                    "error": turn.get("error"), "judge_error": score.get("judge_error")}
        parts.append(f'''<details class="trace turn-evidence"><summary>Turn {h(turn.get('turn_index'))} · {h(score.get('verdict', 'UNKNOWN'))}</summary>
{assessments(info)}<h5>Prompt</h5><pre>{h(turn.get('prompt'))}</pre>
<h5>Response</h5><pre>{h(turn.get('response'))}</pre><p>{h(score.get('reasoning'))}</p>
<h5>Execution and guard evidence</h5><pre>{h(json.dumps(evidence, indent=2, ensure_ascii=False))}</pre></details>''')
    return '<h5>Every conversation turn</h5>' + ''.join(parts) if parts else ''


def record_html(row, mode, number=1, duplicates=False):
    prompt = ''.join(f'<div class="turn"><span>Turn {i}</span><pre>{h(t)}</pre></div>' for i, t in enumerate(prompt_turns(row), 1))
    caution = utility_caveat(row)
    note = f'<div class="callout small">{h(caution)}</div>' if caution else ''
    trace = row.get("guard_trace") or []
    blockers = [str(t.get("layer", "Unknown")) for t in trace if isinstance(t, dict) and t.get("action") in ("block", "review")]
    layer_text = '<div class="trace-pills">' + ''.join(f'<span>{h(t)}</span>' for t in blockers) + '</div>' if blockers else ''
    trace_blob = json.dumps({"guard_trace": trace, "tool_trace": row.get("tool_trace") or []}, indent=2, ensure_ascii=False)
    duplicate_label = f" · record {number}" if duplicates else ""
    return f'''<section class="record"><div class="record-head"><h4>{h(mode.title() + duplicate_label)}</h4>{badge(verdict(row))}</div>
<div class="record-meta">{h(row.get('model') or 'Model not recorded')} · {h(row.get('timestamp') or 'Time not recorded')}</div>
{note}{assessments(row)}<h5>Prompt</h5>{prompt}<h5>Final response</h5><pre class="response">{h(row.get('response') or 'Not recorded')}</pre>
<h5>Stored scoring reason</h5><p>{h(row.get('reasoning') or 'Not recorded')}</p>
<div class="score-meta">Rules: {h(row.get('rule_verdict') or 'Unavailable')}<span>Judge: {h(row.get('judge_verdict') or 'Unavailable')}</span></div>{layer_text}
{turn_evidence(row)}<details class="trace"><summary>Inspect combined tool and guard evidence</summary><pre>{h(trace_blob)}</pre></details></section>'''


def evidence_card(aid, group, paired):
    base = (group["unguarded"] or group["guarded"])[0]
    all_rows = group["unguarded"] + group["guarded"]
    scores = {verdict(r) for r in all_rows}
    caveat = any(utility_caveat(r) for r in all_rows)
    score_attrs = " ".join(sorted(scores)) + (" UTILITY" if caveat else "")
    panels, pills = [], []
    for mode in MODES:
        rows = group[mode]
        if not rows:
            panels.append(f'<div class="record empty">{mode.title()}<br>No evidence supplied for this ID.</div>')
            pills.append(f'<span class="mode-badge">{mode[0].upper()} <span class="badge unknown">MISSING</span></span>')
        else:
            panels.append('<div>' + ''.join(record_html(row, mode, i, len(rows) > 1) for i, row in enumerate(rows, 1)) + '</div>')
            pills.append(f'<span class="mode-badge">{mode[0].upper()} ' + ' '.join(badge(verdict(r)) for r in rows) + '</span>')
    search = " ".join(str(row.get(key) or "") for row in all_rows for key in ("id", "family", "objective", "prompt", "turns", "response", "reasoning"))
    search += " " + " ".join(str(t.get(key) or "") for row in all_rows
                             for t in row.get("turn_results") or []
                             for key in ("prompt", "response", "score"))
    return f'''<details class="evidence" data-family="{h(family(base))}" data-verdicts="{h(score_attrs)}" data-search="{h(search.lower())}">
<summary><span class="expand" aria-hidden="true">+</span><span class="evidence-name"><strong>{h(aid)}</strong><span>{h(label(family(base)))} · {'Matched inputs + model' if aid in paired else 'Pairing unavailable'}</span></span><span class="evidence-badges">{''.join(pills)}{'<span class="utility-tag">Utility review</span>' if caveat else ''}</span></summary>
<div class="evidence-body"><p class="objective"><strong>Objective</strong> {h(base.get('objective') or 'Not recorded')}</p><div class="record-grid">{''.join(panels)}</div></div></details>'''


CSS = r"""
:root{--bg:#081221;--panel:#101e31;--panel2:#13243a;--border:#263d55;--ink:#eef6ff;--muted:#a9bed1;--cyan:#65ddec;--teal:#5ee0b0;--red:#ff8291;--amber:#ffd180;--radius:18px;--sans:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--mono:ui-monospace,SFMono-Regular,Consolas,monospace;color-scheme:dark}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 var(--sans)}a{color:var(--cyan);text-decoration:none}a:hover{text-decoration:underline}button,input,select{font:inherit}button,a,input,select,summary{touch-action:manipulation}a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid var(--cyan);outline-offset:4px}button{cursor:pointer}.shell{max-width:1376px;margin:auto;padding:28px 44px 56px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:24px;border-bottom:1px solid var(--border);padding-bottom:22px}.brand{display:flex;align-items:center;gap:12px;font-weight:760;letter-spacing:.03em}.brand-icon{display:grid;place-items:center;height:38px;width:38px;border:1px solid #447889;color:var(--cyan);border-radius:11px;background:#173348;font-size:19px}.brand small{display:block;color:var(--muted);font-size:10px;letter-spacing:.16em;font-weight:500}.topbar nav{display:flex;gap:24px;align-items:center;font-size:13px}.print-button{border:1px solid var(--border);border-radius:8px;padding:8px 12px;background:var(--panel2);color:var(--ink)}.eyebrow{font:11px var(--mono);letter-spacing:.17em;color:var(--cyan);text-transform:uppercase}.hero{padding:48px 0 29px;display:grid;grid-template-columns:1fr auto;align-items:end;gap:30px}.hero h1{font-size:clamp(31px,4.2vw,53px);letter-spacing:-.055em;line-height:1.08;margin:15px 0 20px;max-width:840px}.hero h1 span{color:var(--cyan)}.hero p{max-width:780px;color:var(--muted);font-size:16px;margin:0}.snapshot{color:var(--muted);font:12px/1.7 var(--mono);border-left:1px solid var(--border);padding:12px 0 12px 22px;white-space:nowrap}.snapshot strong{display:block;color:var(--ink);font:650 14px var(--sans);margin-bottom:7px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:8px 0 20px}.stat{background:linear-gradient(140deg,#142941,var(--panel));border:1px solid var(--border);padding:23px;border-radius:var(--radius)}.stat-label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em;min-height:38px}.stat-value{font-size:39px;font-weight:680;letter-spacing:-.04em;margin:3px 0}.stat-value small{font-size:19px;color:var(--muted);font-weight:500}.stat-note{font-size:12px;color:var(--muted)}.stat.fail-stat .stat-value{color:var(--red)}.stat.safe-stat .stat-value{color:var(--teal)}.callout{border:1px solid #735e3b;border-left:3px solid var(--amber);border-radius:11px;background:#29271f;padding:16px 20px;color:#f0d9b0;font-size:13px}.callout strong{display:block;color:var(--amber);font-size:14px;margin-bottom:3px}.callout.small{font-size:12px;margin:14px 0;padding:10px 13px}.section-heading{display:flex;align-items:start;justify-content:space-between;gap:22px;margin:37px 0 17px}.section-heading h2{font-size:23px;letter-spacing:-.035em;margin:0}.section-heading p{color:var(--muted);font-size:13px;margin:5px 0 0}.section-number{font:11px var(--mono);letter-spacing:.1em;color:var(--cyan);margin-bottom:6px}.split{display:grid;grid-template-columns:1.2fr 1fr;gap:19px}.panel{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:25px}.panel h3{font-size:16px;margin:0 0 4px}.panel .sub{color:var(--muted);font-size:12px;margin:0 0 21px}.mode-line{display:flex;justify-content:space-between;gap:10px;font-size:13px;font-weight:650;margin:19px 0 9px}.mode-line .count{color:var(--muted);font:12px var(--mono);font-weight:400}.stack{display:flex;overflow:hidden;height:16px;border-radius:4px;background:#25374b}.stack .pass{background:var(--teal)}.stack .fail{background:var(--red)}.stack .warn{background:var(--amber)}.stack .error,.stack .unknown{background:#8796ab}.bar-caption{display:flex;justify-content:space-between;gap:8px;color:var(--muted);font:11px var(--mono);margin-top:8px;flex-wrap:wrap}.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:22px;color:var(--muted);font-size:11px}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px}.dot.fail{background:var(--red)}.dot.warn{background:var(--amber)}.dot.pass{background:var(--teal)}.dot.unknown{background:#8796ab}.paired{border-top:1px solid var(--border);margin-top:23px;padding-top:17px;font-size:13px;color:var(--muted)}.paired strong{color:var(--ink)}.quality-metric{display:flex;align-items:baseline;justify-content:space-between;border-bottom:1px solid var(--border);padding:13px 0;font-size:13px}.quality-metric:first-of-type{padding-top:0}.quality-metric strong{font:650 18px var(--mono);color:var(--cyan)}.quality-note{font-size:12px;color:var(--muted);margin-bottom:0}.table-wrap{overflow:auto;border:1px solid var(--border);border-radius:var(--radius)}table{width:100%;border-collapse:collapse;font-size:13px}th{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);background:#102136;text-align:left}th,td{padding:17px 20px;border-bottom:1px solid var(--border);vertical-align:middle}tr:last-child td{border-bottom:0}tbody tr{background:var(--panel)}tbody tr:hover{background:var(--panel2)}td:first-child{font-weight:550}.family-cell{min-width:210px}.family-cell small{display:block;color:var(--muted);font-size:11px;font-weight:400}.heat{display:inline-flex;min-width:65px;justify-content:center;align-items:center;padding:5px 9px;border-radius:7px;font-weight:650;font-family:var(--mono);background:#1c3938;color:var(--teal)}.heat.risk{background:#52313d;color:#ffb1ba}.heat.no-data{background:#223146;color:var(--muted)}.matrix-counts{display:inline-block;color:var(--muted);font:11px var(--mono);margin-left:12px}.utility-row{border-top:2px solid #536379}.utility-row td{background:#1a2637}.controls-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:13px}.control{background:var(--panel);border:1px solid var(--border);border-radius:13px;padding:18px}.control span{font:10px var(--mono);color:var(--cyan);text-transform:uppercase;letter-spacing:.07em}.control h3{font-size:14px;line-height:1.35;margin:10px 0}.control p{color:var(--muted);font-size:12px;margin:0}.filterbar{display:grid;grid-template-columns:1fr 240px 220px;gap:12px;margin-bottom:13px}.field label{display:block;font-size:11px;color:var(--muted);margin:0 0 6px}.field input,.field select{width:100%;border:1px solid var(--border);border-radius:9px;padding:11px 12px;background:var(--panel);color:var(--ink);min-height:45px}.filter-status{font-size:12px;color:var(--muted);margin:12px 0}.evidence{border:1px solid var(--border);background:var(--panel);border-radius:12px;margin:10px 0;overflow:hidden}.evidence>summary{display:flex;align-items:center;gap:15px;list-style:none;padding:18px;cursor:pointer}.evidence>summary::-webkit-details-marker{display:none}.expand{font:23px var(--mono);color:var(--cyan);flex:0 0 16px}.evidence[open]>summary{border-bottom:1px solid var(--border)}.evidence[open]>summary .expand{transform:rotate(45deg)}.evidence-name{min-width:0;flex:1}.evidence-name strong{font-size:14px;overflow-wrap:anywhere}.evidence-name>span{display:block;font-size:11px;color:var(--muted);margin-top:3px}.evidence-badges{display:flex;gap:14px;align-items:center;flex-wrap:wrap;justify-content:flex-end}.mode-badge{display:inline-flex;align-items:center;gap:7px;color:var(--muted);font:11px var(--mono)}.badge{display:inline-flex;align-items:center;font:650 10px var(--mono);padding:4px 7px;border-radius:5px;letter-spacing:.03em}.badge.fail{color:#ffb2bb;background:#4c2e3c}.badge.warn{color:var(--amber);background:#453b29}.badge.pass{color:var(--teal);background:#173d3a}.badge.error,.badge.unknown{color:#d1dceb;background:#354258}.utility-tag{font-size:10px;color:var(--amber);border:1px solid #735e3b;border-radius:5px;padding:3px 6px}.evidence-body{padding:0 18px 19px;border-top:1px solid var(--border)}.objective{font-size:13px;color:var(--muted);margin:17px 0}.objective strong{color:var(--cyan);font-size:10px;text-transform:uppercase;margin-right:8px}.record-grid{display:grid;grid-template-columns:1fr 1fr;gap:15px}.record{border:1px solid var(--border);border-radius:10px;padding:18px;background:#0c192a;min-width:0}.record+.record{margin-top:15px}.record-head{display:flex;justify-content:space-between;align-items:center}.record h4{margin:0;font-size:14px}.record-meta{font:10px var(--mono);color:var(--muted);margin-top:8px;overflow-wrap:anywhere}.record h5{font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:var(--cyan);margin:21px 0 9px}.record p{font-size:12px;color:var(--muted)}pre{font:12px/1.6 var(--mono);white-space:pre-wrap;overflow-wrap:anywhere;margin:0}.response{max-height:330px;overflow:auto}.turn{border-left:2px solid var(--border);padding:0 0 0 11px;margin:11px 0}.turn>span{font-size:10px;color:var(--muted)}.score-meta{display:flex;justify-content:space-between;gap:10px;color:var(--muted);font-size:11px;margin-top:16px}.trace-pills{display:flex;gap:5px;flex-wrap:wrap;margin-top:12px}.trace-pills span{font:10px var(--mono);padding:4px 6px;color:var(--cyan);background:#18344a;border-radius:5px}.trace{margin-top:15px;color:var(--muted);font-size:11px}.trace summary{cursor:pointer}.trace pre{font-size:10px;max-height:400px;overflow:auto;padding:13px 0}.empty{color:var(--muted);text-align:center;padding:35px 20px;background:#101b2a;border:1px dashed var(--border);border-radius:10px}.empty.compact{padding:12px;font-size:12px}.provenance-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.provenance .label{font-size:10px;text-transform:uppercase;color:var(--muted);letter-spacing:.08em;display:block;margin:16px 0 4px}.provenance p{font:12px/1.7 var(--mono);margin:0;overflow-wrap:anywhere}.provenance .hash{font-size:10px;color:var(--muted)}.limits{margin-top:19px}.limits li{font-size:13px;color:var(--muted);margin:10px 0}.limits ul{padding-left:20px;margin-bottom:0}.limits .warnings li{color:#f0d9b0}.footer{display:flex;justify-content:space-between;gap:20px;margin-top:35px;padding-top:23px;border-top:1px solid var(--border);font-size:11px;color:var(--muted)}[hidden]{display:none!important}noscript{display:block;padding:12px;background:#29271f;color:var(--amber)}
@media(max-width:1000px){.shell{padding:24px}.stats{grid-template-columns:repeat(2,1fr)}.hero{grid-template-columns:1fr}.snapshot{display:none}.filterbar{grid-template-columns:1fr 1fr}.field:first-child{grid-column:1/-1}.controls-grid{grid-template-columns:repeat(2,1fr)}.split{grid-template-columns:1fr}.matrix-counts{display:block;margin:6px 0 0}.topbar nav{gap:14px}}
@media(max-width:620px){.shell{padding:16px}.topbar nav a{display:none}.hero{padding-top:32px}.hero p{font-size:14px}.stats{gap:10px}.stat{padding:15px}.stat-value{font-size:31px}.stat-label{font-size:10px;min-height:32px}.stat-note{font-size:11px}.controls-grid,.record-grid,.provenance-grid{grid-template-columns:1fr}.filterbar{grid-template-columns:1fr}.field:first-child{grid-column:auto}.evidence>summary{flex-wrap:wrap;gap:10px;padding:14px}.evidence-badges{width:100%;justify-content:flex-start;padding-left:25px;gap:10px}.section-heading h2{font-size:21px}.panel{padding:18px}th,td{padding:13px}.footer{flex-direction:column}.score-meta{flex-wrap:wrap}.stat-value small{font-size:15px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{ :root{color-scheme:light;--bg:#fff;--panel:#fff;--panel2:#f5f7fa;--border:#b8c5d1;--ink:#182738;--muted:#47586b;--cyan:#006375;--teal:#006448;--red:#a8243a;--amber:#78540a}body{font-size:10px;background:#fff}.shell{max-width:none;padding:0}.topbar nav,.filterbar,.filter-status,.print-button,.expand{display:none}.hero{padding:22px 0}.hero h1{font-size:31px}.hero p{font-size:12px}.hero,.stats,.split,.provenance-grid,.record-grid{break-inside:avoid}.stats{gap:9px}.stat{background:#f5f8fc;padding:12px}.stat-label{font-size:9px;min-height:26px}.stat-value{font-size:27px}.stat-note{font-size:10px}.section-heading{margin-top:25px}.section-heading h2{font-size:19px}.panel,.control,.record,tbody tr,.utility-row td{background:#fff}.callout{color:#523a16;background:#fff9e9;border-color:#b89851}.callout strong{color:#654715}.record{padding:12px}.record p,.limits li{font-size:10px}.evidence{break-inside:auto;margin:15px 0}.evidence>summary{break-after:avoid}.evidence-name strong{font-size:12px}.record-grid{display:block}.record-grid>div+div{margin-top:14px}.response,.trace pre{max-height:none;overflow:visible}pre{font-size:10px}.trace pre{font-size:9px}.evidence[hidden]{display:block!important}.limits .warnings li{color:#78540a}.badge.pass,.heat{background:#d9eee3;color:#07513b}.badge.fail,.heat.risk{background:#f9e0e5;color:#9f1830}.badge.warn{background:#f8eccf;color:#6c4e02}.control{break-inside:avoid}.footer{font-size:9px}.table-wrap{overflow:visible}th,td{padding:10px 12px}thead{display:table-header-group}a{color:#005e70}.trace{display:block}.snapshot{display:none}.no-results{display:none!important}@page{size:A4;margin:14mm}}
"""

JS = r"""
const cards = Array.from(document.querySelectorAll('.evidence'));
const search = document.getElementById('search');
const family = document.getElementById('family');
const verdict = document.getElementById('verdict');
function filterEvidence(){
 const query = search.value.trim().toLowerCase();
 let count = 0;
 cards.forEach(card => {
  const show = (!query || card.dataset.search.includes(query)) &&
   (!family.value || card.dataset.family === family.value) &&
   (!verdict.value || card.dataset.verdicts.split(' ').includes(verdict.value));
  card.hidden = !show;
  if(show) count++;
 });
 document.getElementById('filter-count').textContent = count + ' of ' + cards.length + ' evidence IDs shown';
 document.getElementById('no-results').hidden = count !== 0;
}
search.addEventListener('input',filterEvidence);
family.addEventListener('change',filterEvidence);
verdict.addEventListener('change',filterEvidence);
document.getElementById('print').addEventListener('click',() => window.print());
let savedOpen = [];
window.addEventListener('beforeprint', () => {
 savedOpen = Array.from(document.querySelectorAll('details')).map(el => [el,el.open]);
 savedOpen.forEach(([el]) => el.open = true);
});
window.addEventListener('afterprint', () => savedOpen.forEach(([el,open]) => el.open = open));
filterEvidence();
"""


def render(data):
    u, g = data["modes"]["unguarded"], data["modes"]["guarded"]
    pairs = data["adversarial_pairs"]
    family_count = len([f for f in data["families"] if f != "benign"])
    unique_attacks = sum(family((group["unguarded"] or group["guarded"])[0]) != "benign" for group in data["groups"].values())
    benign_count = len(data["groups"]) - unique_attacks
    gaps = sum(len(data["modes"][m]["utility_gaps"]) for m in MODES)
    missing_judge = sum(data["modes"][m]["missing_judge"] for m in MODES)
    caveat_text = (f"{gaps} benign record(s) have failed, unassessed or visibly incomplete answers. " if gaps else "") + (f"Judging is unavailable for {missing_judge} benign record(s). " if missing_judge else "") + "Independent answer checks measure minimum expected facts. Review full responses before claiming complete correctness or preserved utility."
    stamps = sorted(u["timestamps"] + g["timestamps"])
    date_label = stamps[-1][:10] if stamps else "No run timestamp"
    stats = f'''<div class="stats">
<div class="stat"><div class="stat-label">Adversarial coverage</div><div class="stat-value">{unique_attacks}<small> IDs</small></div><div class="stat-note">{family_count} attack families · {benign_count} separate benign IDs</div></div>
<div class="stat fail-stat"><div class="stat-label">Unguarded / adversarial FAIL</div><div class="stat-value">{fraction(u['attack_counts'].get('FAIL',0),len(u['attacks']))}</div><div class="stat-note">Stored failures / attempted attack records</div></div>
<div class="stat safe-stat"><div class="stat-label">Guarded / adversarial FAIL</div><div class="stat-value">{fraction(g['attack_counts'].get('FAIL',0),len(g['attacks']))}</div><div class="stat-note">Observed sample; no security guarantee</div></div>
<div class="stat"><div class="stat-label">Inputs + model matched</div><div class="stat-value">{len(pairs)}<small> attack IDs</small></div><div class="stat-note">{len(data['paired_ids'])} total pairs · {len(data['unmatched_ids'])} unpaired IDs</div></div></div>'''
    bars = ''.join(f'<div class="mode-line"><span>{mode.title()}</span><span class="count">{len(data["modes"][mode]["attacks"])} attempted attacks</span></div>{stack(data["modes"][mode]["attacks"])}' for mode in MODES)
    paired_text = f"<strong>{data['paired_fail']['unguarded']}/{len(pairs)} → {data['paired_fail']['guarded']}/{len(pairs)} recorded FAIL</strong><br>Unguarded → guarded among {len(pairs)} matched adversarial IDs. Schema 2 also matches evaluation settings and source fingerprints; legacy metadata may be incomplete." if pairs else "<strong>Matched comparison unavailable</strong><br>No unique attack IDs with compatible inputs, model and recorded evaluation configuration are available in both modes."
    benign_bars = ''.join(f'<div class="mode-line"><span>{mode.title()} benign</span><span class="count">{len(data["modes"][mode]["benign"])} records</span></div>{stack(data["modes"][mode]["benign"])}' for mode in MODES)
    utility_rows = ''.join(f'<tr><th scope="row">{mode.title()}</th>' + ''.join(
        f'<td>{data["modes"][mode]["utility_counts"].get(v, 0)}</td>'
        for v in ("PASS", "FAIL", "UNASSESSED")) + '</tr>' for mode in MODES)
    utility_table = '<h3 style="margin-top:24px">Independent answer quality</h3><p class="sub">Schema 2 uses explicit expected-answer checks. Legacy utility is unassessed.</p><div class="table-wrap"><table><thead><tr><th>Mode</th><th>PASS</th><th>FAIL</th><th>Unassessed</th></tr></thead><tbody>' + utility_rows + '</tbody></table></div>'
    table_rows = []
    for fam in data["families"]:
        cells = []
        for mode in MODES:
            rows = [r for r in data["modes"][mode]["rows"] if family(r) == fam]
            counts = Counter(verdict(r) for r in rows)
            css = "risk" if counts["FAIL"] else "" if rows else "no-data"
            count_label = f'{counts["FAIL"]}/{len(rows)}' if rows else "—"
            stats_label = " · ".join(f"{counts[v]} {v}" for v in VERDICTS if counts[v]) if rows else "No evidence"
            cells.append(f'<td><span class="heat {css}">{count_label}</span><span class="matrix-counts">{h(stats_label)}</span></td>')
        table_rows.append(f'<tr class="{"utility-row" if fam == "benign" else ""}"><td class="family-cell">{h(label(fam))}<small>{"Separate utility / benign safety group" if fam == "benign" else "Adversarial test family"}</small></td>{"".join(cells)}</tr>')
    table = '<div class="table-wrap"><table><thead><tr><th scope="col">Test family</th><th scope="col">Unguarded · FAIL / n</th><th scope="col">Guarded · FAIL / n</th></tr></thead><tbody>' + ''.join(table_rows) + '</tbody></table></div>' if table_rows else '<div class="empty">No family evidence available.</div>'
    controls = ''.join(f'<article class="control"><span>{h(DEFENSE_MAP.get(fam, ("Define a control", "To review"))[1])}</span><h3>{h(label(fam))}</h3><p>{h(DEFENSE_MAP.get(fam, ("Define a family-specific control", "To review"))[0])}</p></article>' for fam in data["families"])
    options = ''.join(f'<option value="{h(fam)}">{h(label(fam))}</option>' for fam in data["families"])
    ordered = sorted(data["groups"].items(), key=lambda item: (min(VERDICTS.index(verdict(r)) for rows in item[1].values() for r in rows), item[0]))
    cards = ''.join(evidence_card(aid, group, data["paired_ids"]) for aid, group in ordered)
    provenance = []
    for mode in MODES:
        info = data["modes"][mode]
        times = info["timestamps"]
        times_label = f'{times[0]} → {times[-1]}' if times else 'Not recorded'
        state = f"{info['total']} records" if info["total"] else "Empty evidence" if info["available"] else "No file supplied"
        config_html = ''.join('<details class="trace"><summary>Recorded evaluation configuration</summary><pre>' + h(json.dumps(config, indent=2, ensure_ascii=False)) + '</pre></details>' for config in info['evaluation_configs'])
        provenance.append(f'''<section class="panel provenance"><h3>{mode.title()} <span class="badge unknown">{h(state)}</span></h3><span class="label">Recorded model(s)</span><p>{h(', '.join(info['models']) or 'Not recorded')}</p><span class="label">First → last recorded timestamp</span><p>{h(times_label)}</p><span class="label">Source</span><p>{h(info['source'] if info['available'] else 'Not supplied')}</p><span class="label">Execution errors / complete turn records</span><p>{info['execution_errors']} errors · {fraction(info['complete_turn_records'], info['total'])} records with all turn evidence</p>{config_html}<span class="label">SHA-256 · canonical parsed records</span><p class="hash">{h(info['digest'])}</p></section>''')
    warnings = ''.join(f'<li>{h(warning)}</li>' for warning in data["warnings"])
    limitations = ''.join(f'<li>{h(item)}</li>' for item in LIMITATIONS)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="dark light"><title>ARIA · Red-team findings</title><style>{CSS}</style></head>
<body><div class="shell"><header class="topbar"><a class="brand" href="#overview"><span class="brand-icon" aria-hidden="true">A</span><span>NEOBANK / ARIA<small>SECURITY EVALUATION LAB</small></span></a><nav aria-label="Report navigation"><a href="#coverage">Coverage</a><a href="#evidence">Evidence</a><a href="#provenance">Provenance</a><button class="print-button" id="print" type="button">Print / PDF</button></nav></header>
<main><section id="overview" class="hero"><div><div class="eyebrow">Saved evaluation · Evidence-led review</div><h1>Where ARIA holds.<br><span>Where review is still needed.</span></h1><p>Compare recorded adversarial outcomes, inspect the evidence behind each verdict, and keep benign answer quality visible alongside security controls.</p></div><div class="snapshot"><strong>Evidence snapshot</strong>{h(date_label)}<br>{len(data['groups'])} unique test IDs<br>Offline · stored results</div></section>
{stats}<div class="callout"><strong>Utility needs a separate review</strong>{h(caveat_text)}</div>
<section id="coverage"><div class="section-heading"><div><div class="section-number">01 / OUTCOME COMPARISON</div><h2>Security outcomes, with the right denominator</h2><p>Counts retain the original verdicts. Color shows recorded labels; no marker hit is not proof of safety.</p></div></div>
<div class="split"><article class="panel"><h3>Adversarial suite</h3><p class="sub">Benign requests are excluded from these bars.</p>{bars}<div class="legend"><span><i class="dot fail"></i>FAIL · observed rubric failure</span><span><i class="dot warn"></i>WARN · concern</span><span><i class="dot pass"></i>PASS · no flagged failure</span><span><i class="dot unknown"></i>Incomplete</span></div><div class="paired">{paired_text}</div></article>
<article class="panel"><h3>Benign checks</h3><p class="sub">Stored labels include disclosure failures and potentially unhelpful answers.</p>{benign_bars}{utility_table}<div class="paired"><strong>Security and answer quality are separate.</strong><br>{gaps} records need answer-quality review; {missing_judge} benign judge result(s) unavailable.</div></article></div>
<div class="section-heading"><div><div class="section-number">02 / FAMILY BREAKDOWN</div><h2>Find the families that need attention</h2><p>Each cell shows recorded FAIL / attempted records, followed by the full verdict mix.</p></div></div>{table}</section>
<section id="controls"><div class="section-heading"><div><div class="section-number">03 / DEFENSE COVERAGE</div><h2>Connect attack families to controls</h2><p>These are controls to validate. Inspect each evidence card for the guard layers actually recorded.</p></div></div><div class="controls-grid">{controls or '<div class="empty">No family evidence for control mapping.</div>'}</div></section>
<section id="evidence"><div class="section-heading"><div><div class="section-number">04 / EVIDENCE EXPLORER</div><h2>Inspect the response behind the score</h2><p>Expand a test to compare prompts, responses, reasons, and tool traces. U = unguarded; G = guarded.</p></div></div>
<div class="filterbar"><div class="field"><label for="search">Search evidence</label><input id="search" type="search" placeholder="Search ID, prompt, response or reasoning…" autocomplete="off"></div><div class="field"><label for="family">Test family</label><select id="family"><option value="">All families</option>{options}</select></div><div class="field"><label for="verdict">Any stored verdict / caveat</label><select id="verdict"><option value="">All evidence</option><option value="FAIL">FAIL in either mode</option><option value="WARN">WARN in either mode</option><option value="PASS">PASS in either mode</option><option value="ERROR">ERROR in either mode</option><option value="UNKNOWN">Unknown verdict</option><option value="UTILITY">Needs utility review</option></select></div></div>
<noscript>Search filters require JavaScript. All evidence is available below without it.</noscript><p id="filter-count" class="filter-status" role="status" aria-live="polite">{len(data['groups'])} evidence IDs</p>{cards}<div class="empty no-results" id="no-results" hidden>No evidence matches these filters. Clear the search or select all families and verdicts.</div>{'' if cards else '<div class="empty">No evidence records available. Run the suite, then regenerate this report.</div>'}</section>
<section id="provenance"><div class="section-heading"><div><div class="section-number">05 / PROVENANCE & LIMITATIONS</div><h2>Know what this snapshot can support</h2><p>Generated entirely from saved JSONL records. No model calls and no result rewriting.</p></div></div><div class="provenance-grid">{''.join(provenance)}</div><article class="panel limits"><h3>Evidence quality notes</h3><ul class="warnings">{warnings or '<li>No missing-file, pairing, timestamp or visible answer-gap warnings detected. The limitations below still apply.</li>'}</ul><h3 style="margin-top:24px">Interpretation boundaries</h3><ul>{limitations}</ul><p class="quality-note">Source-level findings are maintained separately in <code>docs/code_review.md</code> (Code review tab in the app). Prompt-suite results do not verify the login boundary, every error path, or the current implementation.</p></article></section>
</main><footer class="footer"><span>ARIA evaluation lab · Fictional banking fixture · Saved evidence</span><span>Generated by python -m redteam.report · <code>docs/findings_report.md</code> companion</span></footer></div><script>{JS}</script></body></html>'''
