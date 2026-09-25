"""Look and feel of the Streamlit app: CSS and rupee formatting."""

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

:root {
    --ink: #edf5ff;
    --muted: #9aabc0;
    --line: #263852;
    --blue: #4ea1ff;
    --mint: #9de9cf;
    --amber: #f2c46d;
    --surface: #132238;
}

.stApp {
    background:
        radial-gradient(circle at 8% 0%, rgba(41, 89, 142, .28), transparent 28rem),
        radial-gradient(circle at 96% 20%, rgba(24, 111, 107, .16), transparent 24rem),
        #091321;
    font-family: 'DM Sans', sans-serif;
}
.block-container { max-width: 1180px; padding: 4.2rem 2rem 4rem; }
h1, h2, h3, h4 { font-family: 'Space Grotesk', sans-serif; letter-spacing: -0.03em; }

/* ---- hero ---- */
.hero {
    background:
        linear-gradient(120deg, rgba(9, 22, 42, .92), rgba(17, 60, 87, .84)),
        radial-gradient(circle at 85% 20%, #2b8a8a, transparent 22rem);
    border-radius: 26px;
    padding: 2.3rem 2.6rem;
    position: relative;
    overflow: hidden;
    margin-bottom: 1.1rem;
    border: 1px solid rgba(157, 233, 207, .18);
    box-shadow: 0 22px 55px rgba(0, 0, 0, .24);
}
.hero:after {
    content: '✦'; position: absolute; right: 5%; top: 6%;
    font-size: 10rem; line-height: 1; color: rgba(255,255,255,.07); transform: rotate(15deg);
}
.eyebrow { color: var(--mint); font-weight: 700; letter-spacing: .14em; text-transform: uppercase; font-size: .74rem; margin-bottom: .7rem; }
.hero h1 { color: white; font-size: clamp(2rem, 4.6vw, 3.6rem) !important; line-height: 1.04 !important; margin: 0; max-width: 680px; }
.hero p { color: #d7e5f5; max-width: 600px; font-size: 1.02rem; margin: .9rem 0 0; }
.badges { display: flex; flex-wrap: wrap; gap: .5rem; margin-top: 1.3rem; }
.badge {
    background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.2);
    color: #e8f2ff; padding: .4rem .75rem; border-radius: 999px; font-size: .78rem;
}

/* ---- cards ---- */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 20px;
    box-shadow: 0 14px 32px rgba(0, 0, 0, .18);
}
.section-label { color: #82a1c4; font-size: .76rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; margin: .6rem 0 .5rem; }
.kpi { background: rgba(19, 34, 56, .85); border: 1px solid var(--line); border-radius: 16px; padding: 1rem 1.1rem; height: 100%; }
.kpi .label { color: var(--muted); font-size: .74rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
.kpi .value { color: var(--mint); font-family: 'Space Grotesk', sans-serif; font-size: 1.8rem; font-weight: 700; line-height: 1.2; margin-top: .2rem; }
.kpi .sub { color: var(--muted); font-size: .78rem; margin-top: .15rem; }

/* ---- estimate result ---- */
.result-card {
    background: linear-gradient(135deg, #0f2949, #1d5277);
    border-radius: 20px; padding: 1.5rem 1.7rem; margin-bottom: .8rem;
}
.result-card .label { color: #b7d9ee; font-size: .78rem; font-weight: 700; letter-spacing: .1em; }
.result-card .price { color: white; font-family: 'Space Grotesk', sans-serif; font-size: 2.9rem; font-weight: 700; line-height: 1.1; margin: .25rem 0; }
.result-card .rupees { color: #d0e4f2; font-size: .92rem; }
.range { margin-top: 1.1rem; }
.range-track { position: relative; height: 10px; border-radius: 999px; background: rgba(255,255,255,.14); }
.range-fill { position: absolute; top: 0; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #4ea1ff, #9de9cf); }
.range-dot { position: absolute; top: -5px; width: 20px; height: 20px; margin-left: -10px; border-radius: 50%; background: white; border: 4px solid #0f2949; box-shadow: 0 0 0 2px #9de9cf; }
.range-labels { display: flex; justify-content: space-between; color: #d0e4f2; font-size: .8rem; margin-top: .55rem; }
.stat { background: #102f3a; border: 1px solid #1b5b62; border-radius: 14px; padding: .8rem; text-align: center; height: 100%; }
.stat strong { color: #8ce0c2; font-size: 1.15rem; display: block; font-family: 'Space Grotesk', sans-serif; }
.stat span { color: #a2c8c2; font-size: .74rem; }
.tip, .warn {
    border-radius: 0 10px 10px 0; padding: .7rem 1rem; font-size: .86rem; margin: .6rem 0;
}
.tip { background: #14283f; border-left: 4px solid var(--blue); color: #b9d6f5; }
.warn { background: #2b281c; border-left: 4px solid var(--amber); color: #f2d58e; }

/* ---- controls ---- */
.stButton > button[kind="primary"], .stButton > button {
    border-radius: 11px; font-weight: 700; transition: transform .15s ease;
}
.stButton > button:hover { transform: translateY(-1px); }
button[data-baseweb="tab"] { font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 1rem; }
label, [data-testid="stWidgetLabel"] p { font-weight: 600 !important; }
.footer-note { color: var(--muted); font-size: .78rem; margin-top: 1.5rem; }
.dot-ok { color: #3fbf95; font-weight: 700; }
.dot-warn { color: #e29a55; font-weight: 700; }

@media (max-width: 700px) {
    .block-container { padding: 3.8rem 1rem 3rem; }
    .hero { padding: 1.8rem 1.4rem; border-radius: 20px; }
    .hero:after { font-size: 6rem; }
    .result-card .price { font-size: 2.3rem; }
}
</style>
"""


def format_lakh(value: float) -> str:
    """3.77 -> '₹3.77 lakh'; 105 -> '₹1.05 crore'."""
    if value >= 100:
        return f"₹{value / 100:,.2f} crore"
    return f"₹{value:,.2f} lakh"


def format_rupees(lakh: float) -> str:
    """Full amount with Indian digit grouping: 3.77 -> '₹3,77,000'."""
    digits = str(int(round(lakh * 100_000)))
    if len(digits) <= 3:
        return f"₹{digits}"
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "₹" + ",".join(groups + [tail])
