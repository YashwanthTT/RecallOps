# Step 0 — UI audit (before)

Observed with the app running at `http://localhost:8501` (Chrome, 1280×900 and 900px checks), plus DOM inspection.

## Blocking bugs

1. **Material icon font is broken.** `html, body, [class*="st-"] { font-family: Inter }` matches every Streamlit element, including `<span data-testid="stIconMaterial">`. Computed font on the expander chevron is `Inter`, so the glyph name `keyboard_arrow_right` is painted as text (`_arrow_right` overlapping the expander label). Same risk for every `st.code` copy button and toast close button.
2. **Sidebar bank identity wraps and is a raw link.** `https://api.hindsight.vectorize.io · bank incident-response-agent` wraps onto two lines, the URL is an ordinary blue link, and the bank id is not visually separated.
3. **Sidebar metric cards clip at 1280px.** The two `st.metric` columns plus the 1080px content max-width leave the sidebar text tight; labels truncate (`ts`, `Memories`).

## Layout / design-system issues

- Content column is only ~820px of usable width while 1100px is requested; 80px side padding and a 1080px cap create dead space.
- No single token set: colours, radii, and font sizes are scattered in one long CSS block.
- Tabs are a plain underlined text row; no nav bar, no rounded frame around the workspace.
- Cards are 14px radius with inconsistent inner spacing; no 8px rhythm.
- Type scale is ad hoc (`1.9rem`, `1.25rem`, `1rem`, `0.9rem`, `0.82em`).
- Muted text (`#8b95a7`) is borderline for 4.5:1 on the dark surface.
- Inline-code hints (`Title:`, `Service:`, `Root cause:`) are tiny and hard to scan.

## Screen-by-screen

### Briefing
- Empty bank shows only a sidebar button; the main area says "Seed memory in the sidebar, then run the briefing."
- One long `<select>` + three inputs + a 180px textarea. No scenario cards.
- Results are two raw Markdown walls side by side. No visual hierarchy, no "Avoid this" at the top.
- Impact metrics are three `st.metric`s below the run; not sticky.
- Commands are inline backticks, no copy affordance, no approval warning.
- Recalled memories are one expander containing raw text and scores.

### Service monitor
- Four metric cards show "Operational" as the value with an up-arrow delta for p95; colour-only status.
- Break/probe controls are plain forms; no incident banner hierarchy.
- Briefing output repeats the raw two-column wall.

### OneUptime intake
- No stepper. Paste area has a tiny JSON placeholder and a "Load sample payload" button above it.
- Parsed fields are editable but appear below a raw-JSON caption; no friendly validation summary.
- Parse errors print `TypeName: message`; no friendly card.
- Webhook expander is the only expander and shows the literal `_arrow_right` bug.

### Close the loop
- No severity field. "What did NOT work" is not labelled as the negative-memory field.
- After retaining, no path back to the Briefing tab.
- Learned list is a plain bullet list.

### Reflect
- One selectbox + button + raw Markdown answer. No chat shape, no suggested chips, no sources.
- Empty state is a caption.

### Integration guide
- Long wall of code blocks; only one collapsible section. No "webhook endpoints" collapsible block.

## States / accessibility

- Spinners are generic ("Running the baseline, then recalling history…").
- Errors print exception class + message inline; no retry card.
- Focus states are browser defaults; no consistent visible focus ring.
- No icon + text pairing on status colours (green/red only).
- At ~900px the four-column metric row and two-column comparison get cramped.
