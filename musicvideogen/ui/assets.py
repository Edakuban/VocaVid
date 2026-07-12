from __future__ import annotations

from html import escape


def _text(value) -> str:
    return escape(str(value), quote=False)


def _page(title: str, body: str, queue_count: int = 0) -> str:
    browser_title = _browser_title(title, queue_count)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_text(browser_title)}</title>
  <link rel="icon" type="image/x-icon" href="/icon/favicon.ico">
  <style>
    :root {{
      color-scheme: dark;
      --bg-app: #0b1012;
      --bg-header: #0d1316;
      --bg-elevated: #12191d;
      --bg-panel: #171f23;
      --bg-card: #182126;
      --bg-card-hover: #202b30;
      --bg-control: #202a2f;
      --bg-control-hover: #253138;
      --border-subtle: #2d393f;
      --border-default: #3a484f;
      --border-strong: #526169;
      --text-primary: #f2f5f6;
      --text-secondary: #bcc5ca;
      --text-muted: #7f8c93;
      --text-disabled: #59656b;
      --accent: #e9489f;
      --accent-hover: #f15bad;
      --accent-soft: rgba(233,72,159,.14);
      --action: #29d3b0;
      --action-hover: #4ce2c2;
      --action-active: #1fb394;
      --action-soft: rgba(41,211,176,.14);
      --success: #45c98d;
      --success-soft: rgba(69,201,141,.10);
      --warning: #f0b84d;
      --warning-soft: rgba(240,184,77,.12);
      --danger: #ee6675;
      --danger-soft: rgba(238,102,117,.12);
      --radius-sm: 6px;
      --radius-md: 9px;
      --radius-lg: 14px;
      --font-ui: "Inter", "Geist", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --studio-bg: var(--bg-app);
      --studio-surface: var(--bg-elevated);
      --studio-surface-2: var(--bg-panel);
      --studio-line: var(--border-subtle);
      --studio-text: var(--text-primary);
      --studio-muted: var(--text-muted);
      --studio-accent: var(--action);
      --studio-pink: var(--accent);
      --studio-amber: var(--warning);
    }}
    body {{
      margin: 0;
      font-family: var(--font-ui);
      background:
        radial-gradient(ellipse 60% 280px at 8% 0%, rgba(41,211,176,.07), transparent 72%),
        radial-gradient(ellipse 55% 260px at 96% 0%, rgba(233,72,159,.055), transparent 72%),
        var(--bg-app);
      color: var(--studio-text);
    }}
    main {{ max-width: none; margin: 0; padding: 24px; }}
    .studio-topbar {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 18px;
      padding: 14px 16px;
      border: 1px solid rgba(255,255,255,.055);
      border-radius: var(--radius-lg);
      background: var(--bg-header);
      color: var(--text-primary);
    }}
    .studio-logo {{ width: 68px; height: 68px; object-fit: contain; flex: 0 0 auto; filter: drop-shadow(0 10px 24px rgba(0,0,0,.32)); }}
    .studio-brand {{ font-size: 23px; font-weight: 750; letter-spacing: -.02em; }}
    .studio-tagline {{ color: var(--studio-muted); font-weight: 650; }}
    .studio-spacer {{ flex: 1; }}
    .studio-panel {{
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      background: var(--bg-panel);
      overflow: hidden;
      box-shadow: 0 24px 80px rgba(0,0,0,.24);
    }}
    .studio-panel-head {{
      padding: 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid var(--border-subtle);
    }}
    .studio-chip {{
      border: 1px solid var(--border-default);
      border-radius: 999px;
      padding: 8px 11px;
      background: var(--bg-control);
      color: var(--text-secondary);
      font-size: 12px;
      font-weight: 850;
      white-space: nowrap;
    }}
    .studio-chip-green {{
      border-color: rgba(69,201,141,.42);
      background: var(--success-soft);
      color: #d7ffeb;
    }}
    .studio-chip-pink {{
      border-color: rgba(233,72,159,.4);
      background: var(--accent-soft);
      color: #ffd7e5;
    }}
    .studio-button {{
      border: 1px solid var(--action);
      border-radius: 12px;
      background: var(--action);
      color: #07120f;
      padding: 10px 13px;
      font-weight: 750;
      cursor: pointer;
      text-decoration: none;
      display: inline-block;
    }}
    .studio-button:hover, .studio-button:focus {{ background: var(--action-hover); border-color: var(--action-hover); outline: none; }}
    .studio-button-secondary {{
      border: 1px solid var(--border-default);
      background: #263238;
      color: #d8dfe2;
    }}
    .studio-button-danger, .danger-button {{
      border: 1px solid rgba(238,102,117,.48);
      background: var(--danger-soft);
      color: #ffd7e5;
    }}
    h1 {{ font-size: 28px; margin: 0; }}
    form, .panel {{ background: var(--bg-panel); border: 1px solid var(--border-subtle); color: var(--text-primary); border-radius: var(--radius-md); padding: 16px; margin-bottom: 16px; }}
    label {{ display: block; color: #c8d0d4; font-size: 12px; font-weight: 650; margin-top: 10px; margin-bottom: 6px; }}
    input, textarea, select {{
      box-sizing: border-box;
      width: 100%;
      border: 1px solid var(--border-default);
      border-radius: 7px;
      background: var(--bg-control);
      color: var(--text-primary);
      padding: 8px;
      font: inherit;
      transition: border-color 150ms ease, box-shadow 150ms ease, background-color 150ms ease;
    }}
    input:hover, textarea:hover, select:hover {{ background: var(--bg-control-hover); border-color: var(--border-strong); }}
    input:focus, textarea:focus, select:focus {{ outline: none; border-color: var(--action); box-shadow: 0 0 0 3px var(--action-soft); }}
    input:disabled, select:disabled, textarea:disabled, input[readonly], textarea[readonly] {{ background: #192126; color: var(--text-disabled); border-color: #2b363c; }}
    ::placeholder {{ color: #69777e; }}
    textarea {{ min-height: 80px; }}
    .prompt-textarea {{ min-width: 260px; min-height: 250px; resize: vertical; }}
    .prompt-actions {{ display: flex; gap: 8px; margin: 6px 0 10px; }}
    .hidden-action-form {{ display: none; }}
    .compact-form {{ padding: 0; margin: 0; border: 0; background: transparent; }}
    .jobs-heading {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    .job-options {{ display: flex; flex-wrap: wrap; gap: 14px; margin-top: 10px; align-items: center; }}
    .job-options label {{ display: inline-flex; gap: 6px; align-items: center; margin: 0; }}
    .job-options input {{ width: auto; }}
    .timing-column {{ width: 11rem; min-width: 11rem; }}
    .timing-form {{ display: grid; grid-template-columns: max-content max-content auto; gap: 4px; align-items: center; }}
    .timing-form input {{ width: 7ch; padding-left: 6px; padding-right: 6px; }}
    .section-form select {{ min-width: 104px; }}
    .approval-label {{ display: inline-flex; align-items: center; gap: 6px; margin: 0; font-weight: 650; }}
    .approval-label input {{ width: auto; }}
    button, .button {{
      border: 1px solid var(--action);
      border-radius: 12px;
      background: var(--action);
      color: #07120f;
      padding: 10px 13px;
      font-weight: 750;
      cursor: pointer;
      text-decoration: none;
      display: inline-block;
      transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease, transform 160ms ease, box-shadow 160ms ease;
    }}
    button:hover, .button:hover, button:focus, .button:focus {{ background: var(--action-hover); border-color: var(--action-hover); outline: none; }}
    button:active, .button:active {{ transform: translateY(0); }}
    .icon-button {{ width: 34px; height: 34px; padding: 0; border-radius: 50%; line-height: 34px; text-align: center; }}
    .actions button {{ border: 1px solid #3a454b; background: #293136; color: #c8d0d4; font-weight: 700; }}
    .actions button:hover, .actions button:focus {{ border-color: rgba(41,211,176,.58); background: #303b40; color: var(--text-primary); }}
    .wip-button {{ border-color: var(--accent); background: var(--accent); color: #fff; box-shadow: inset 0 -2px 0 rgba(0,0,0,.16); }}
    .wip-button:hover, .wip-button:focus {{ background: var(--accent-hover); border-color: var(--accent-hover); color: #fff; }}
    .used-button {{ border-color: #3a454b; background: #263238; color: #d8dfe2; box-shadow: inset 0 -2px 0 rgba(0,0,0,.18); }}
    .used-button::after {{ content: " ✓"; color: var(--success); }}
    .used-button:hover, .used-button:focus {{ background: #303b40; border-color: var(--border-strong); }}
    .actions .wip-button {{ border-color: var(--accent); background: var(--accent); color: #fff; }}
    .actions .wip-button:hover, .actions .wip-button:focus {{ background: var(--accent-hover); border-color: var(--accent-hover); color: #fff; }}
    .actions .used-button {{ border-color: #3a454b; background: #263238; color: #d8dfe2; }}
    .actions .danger-button {{ border-color: rgba(238,102,117,.48); background: var(--danger-soft); color: #ffd7dc; }}
    .danger-panel {{ margin-top: 24px; border-color: rgba(238,102,117,.48); background: transparent; color: var(--danger); }}
    .danger-panel[open] {{ background: transparent; }}
    .danger-panel .compact-form {{ background: transparent; }}
    .danger-button {{ border: 1px solid rgba(238,102,117,.48); background: var(--danger-soft); color: #ffd7dc; }}
    .danger-button:hover, .danger-button:focus {{ background: rgba(238,102,117,.2); border-color: var(--danger); }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; justify-content: center; }}
    .actions form {{ padding: 0; margin: 0; border: 0; background: transparent; }}
    .start-dashboard {{ display: grid; gap: 18px; }}
    .start-hero {{ display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(280px, .65fr); gap: 18px; align-items: stretch; }}
    .start-hero > div, .production-status {{
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      background: var(--bg-panel);
      padding: 22px;
      box-shadow: 0 24px 80px rgba(0,0,0,.22);
    }}
    .start-hero h1 {{ font-size: 42px; line-height: 1.02; margin: 0 0 12px; }}
    .start-hero p {{ max-width: 720px; margin: 0; color: var(--studio-muted); font-size: 17px; line-height: 1.5; }}
    .production-status h2 {{ margin: 0 0 14px; }}
    .stat-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
    .stat {{ border: 1px solid var(--border-subtle); border-radius: 12px; background: var(--bg-elevated); padding: 12px; }}
    .stat strong {{ display: block; font-size: 24px; line-height: 1.1; }}
    .stat span {{ display: block; margin-top: 4px; color: var(--studio-muted); font-size: 12px; font-weight: 800; text-transform: uppercase; }}
    .start-layout {{ display: grid; grid-template-columns: minmax(0, 1fr); gap: 18px; }}
    .project-panel-head {{ flex-wrap: wrap; }}
    .project-browser-controls {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: flex-end; }}
    .project-browser-controls input, .project-browser-controls select {{ width: auto; min-width: 150px; padding: 8px 10px; }}
    .project-browser-controls input {{ min-width: 220px; }}
    .project-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; padding: 16px; }}
    .project-card {{ position: relative; min-width: 0; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--bg-card); overflow: hidden; transition: border-color 160ms ease, transform 160ms ease, box-shadow 160ms ease; }}
    .project-card:hover, .project-card:focus-within {{ border-color: rgba(41,211,176,.55); transform: translateY(-1px); box-shadow: 0 18px 50px rgba(0,0,0,.28); }}
    .project-card-link {{ display: grid; grid-template-rows: auto minmax(0, 1fr); color: var(--studio-text); text-decoration: none; }}
    .project-card-art {{ position: relative; aspect-ratio: 16 / 9; overflow: hidden; background: linear-gradient(135deg, rgba(41,211,176,.32), rgba(233,72,159,.22)); }}
    .project-card-art img, .project-card-art video {{ width: 100%; height: 100%; object-fit: cover; display: block; background: #050708; }}
    .project-card-art video {{ pointer-events: none; }}
    .project-card-art::after {{ content: ""; position: absolute; inset: 0; background: linear-gradient(180deg, transparent 58%, rgba(0,0,0,.38)); pointer-events: none; }}
    .project-card-placeholder {{ position: absolute; inset: 0; display: grid; place-items: center; overflow: hidden; color: rgba(242,245,246,.82); background:
      radial-gradient(circle at 22% 18%, rgba(41,211,176,.42), transparent 28%),
      radial-gradient(circle at 78% 72%, rgba(233,72,159,.34), transparent 30%),
      linear-gradient(135deg, #172126, #0c1114); }}
    .project-card-placeholder::before {{ content: ""; position: absolute; inset: 12px; border: 1px solid rgba(255,255,255,.12); border-radius: var(--radius-md); }}
    .project-card-placeholder-mark {{ position: relative; z-index: 1; display: grid; place-items: center; width: 64px; height: 64px; border: 1px solid rgba(255,255,255,.18); border-radius: 18px; background: rgba(8,13,15,.56); color: #eaf4f1; box-shadow: 0 16px 40px rgba(0,0,0,.25); }}
    .project-card-placeholder-mark::before {{ content: ""; width: 30px; height: 22px; border: 2px solid rgba(234,244,241,.88); border-radius: 6px; box-shadow: inset 0 0 0 1px rgba(41,211,176,.18); }}
    .project-card-placeholder-mark::after {{ content: ""; position: absolute; width: 0; height: 0; border-top: 7px solid transparent; border-bottom: 7px solid transparent; border-left: 11px solid var(--action); transform: translateX(2px); }}
    .project-card-body {{ padding: 12px 14px 14px; min-width: 0; }}
    .project-card-body h3 {{ margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 17px; }}
    .project-card-done {{ border-color: rgba(69,201,141,.58); background: linear-gradient(180deg, rgba(69,201,141,.075), rgba(69,201,141,.025)), var(--bg-card); }}
    .project-card-done .project-card-art {{ background: linear-gradient(135deg, rgba(69,201,141,.38), rgba(69,201,141,.12)); }}
    .project-done-badge {{ position: absolute; right: 10px; top: 10px; z-index: 2; display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 999px; border: 1px solid rgba(69,201,141,.58); background: rgba(218,255,236,.94); color: #0b6d45; font-size: 22px; font-weight: 950; box-shadow: 0 10px 26px rgba(0,0,0,.28); pointer-events: none; }}
    .progress-pill {{ position: relative; display: inline-flex; align-items: center; justify-content: center; min-width: 82px; width: 92px; height: 30px; overflow: hidden; border-radius: 999px; border: 1px solid rgba(255,255,255,.20); background: rgba(9,14,16,.76); color: var(--text-primary); font-size: 12px; font-weight: 900; font-variant-numeric: tabular-nums; box-shadow: 0 10px 26px rgba(0,0,0,.25); }}
    .progress-pill-fill {{ position: absolute; inset: 0 auto 0 0; width: var(--progress, 0%); background: linear-gradient(90deg, rgba(41,211,176,.74), rgba(69,201,141,.76)); }}
    .progress-pill-label {{ position: relative; z-index: 1; text-shadow: 0 1px 8px rgba(0,0,0,.48); }}
    .project-progress-badge {{ position: absolute; left: 10px; top: 10px; z-index: 2; pointer-events: none; }}
    .project-card-hidden {{ display: none; }}
    .project-empty-state {{ display: none; padding: 26px 16px 32px; color: var(--text-muted); text-align: center; font-weight: 750; }}
    .project-empty-state.visible {{ display: block; }}
    .queue-panel {{ display: grid; gap: 14px; }}
    .queue-panel-head {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: end; justify-content: space-between; padding: 16px 16px 0; }}
    .queue-panel-head h2 {{ margin: 0; }}
    .queue-panel-head p {{ margin: 4px 0 0; color: var(--studio-muted); }}
    .queue-summary-grid {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; padding: 0 16px; }}
    .queue-summary-card {{ border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--bg-card); padding: 12px; min-width: 0; }}
    .queue-summary-card-active {{ border-color: rgba(41,211,176,.42); background: var(--action-soft); }}
    .queue-summary-card strong {{ display: block; color: var(--studio-text); font-size: 22px; line-height: 1.1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .queue-summary-card span {{ display: block; margin-top: 5px; color: var(--studio-muted); font-size: 11px; font-weight: 900; text-transform: uppercase; }}
    .jobs-table-wrap {{ overflow-x: auto; padding: 0 16px; }}
    .queue-admin-controls {{ display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: center; justify-content: space-between; padding: 0 16px 16px; }}
    .queue-admin-controls .compact-form {{ margin: 0; }}
    .queue-cleanup-actions {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    .queue-settings-line {{ display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: center; color: var(--text-muted); font-size: 12px; }}
    .queue-settings-line label {{ margin: 0; color: var(--text-muted); font-size: 12px; font-weight: 650; }}
    .queue-settings-line input {{ width: auto; }}
    .queue-job-row[data-href] {{ cursor: pointer; }}
    .queue-job-row[data-href]:hover {{ background: var(--bg-card-hover); }}
    .queue-job-row .queue-job-link-hint {{ color: var(--text-muted); font-size: 11px; }}
    .initial-setup-banner {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; border: 1px solid rgba(41,211,176,.32); border-radius: var(--radius-md); background: var(--action-soft); color: #d8fff4; padding: 12px 14px; font-weight: 750; }}
    .initial-setup-banner span {{ color: var(--text-secondary); font-size: 12px; font-weight: 700; }}
    .modal-content {{ position: relative; width: min(560px, 94vw); max-height: 88vh; overflow: visible; border: 1px solid #344149; border-radius: var(--radius-lg); background: var(--bg-panel); color: var(--text-primary); box-shadow: 0 24px 70px rgba(0,0,0,.55), 0 0 0 1px rgba(255,255,255,.025); }}
    .modal-content > form {{ max-height: calc(88vh - 74px); overflow: auto; }}
    .modal-content .studio-panel-head {{ background: #1b2429; color: var(--text-primary); border-bottom: 1px solid #303c43; }}
    .modal-content h2 {{ margin: 0; }}
    .new-project-form {{ margin: 0; border: 0; border-radius: 0; }}
    .project-list {{ display: grid; grid-template-columns: 1fr; gap: 6px 18px; padding: 8px 10px 4px 26px; }}
    .project-list-item {{ min-width: 0; padding: 4px 8px 4px 0; }}
    .project-list-item a {{ display: inline-block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: calc(100% - 44px); vertical-align: bottom; }}
    .project-list-item.project-done a {{ text-decoration: line-through; color: #66706d; }}
    @media (min-width: 820px) {{ .project-list {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
    @media (min-width: 1240px) {{ .project-list {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
    @media (max-width: 980px) {{
      .start-hero {{ grid-template-columns: 1fr; }}
      .project-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 680px) {{
      main {{ padding: 14px; }}
      .studio-topbar {{ align-items: stretch; flex-direction: column; }}
      .studio-logo {{ width: 52px; height: 52px; }}
      .studio-spacer {{ display: none; }}
      .start-hero h1 {{ font-size: 32px; }}
      .stat-grid, .project-grid, .queue-summary-grid {{ grid-template-columns: 1fr; }}
      .project-card-link {{ grid-template-rows: auto minmax(0, 1fr); }}
    }}
    .project-title-left .progress-pill {{ align-self: center; }}
    .project-topbar {{ position: sticky; top: 0; z-index: 20; margin: -24px -24px 16px; padding: 14px 24px 0; background: rgba(13,19,22,.96); border-bottom: 1px solid rgba(255,255,255,.055); color: var(--text-primary); backdrop-filter: blur(12px); box-shadow: 0 18px 50px rgba(0,0,0,.22); }}
    .project-title-row h1 {{ color: var(--studio-text); text-shadow: 0 1px 18px rgba(0,0,0,.35); }}
    .project-title-row {{ display: grid; grid-template-columns: minmax(180px, 1fr) auto minmax(180px, 1fr); gap: 12px; align-items: center; margin-bottom: 12px; }}
    .project-title-left, .project-title-center, .project-title-right {{ display: flex; align-items: center; gap: 10px; min-width: 0; }}
    .project-title-left {{ justify-content: flex-start; }}
    .project-title-center {{ justify-content: center; }}
    .project-title-right {{ justify-content: flex-end; }}
    .project-title-row .button {{ margin-left: 0; }}
    .project-icon-button {{ width: 42px; height: 42px; display: inline-flex; align-items: center; justify-content: center; padding: 0; border-radius: 12px; border: 1px solid var(--border-default); background: #263238; color: var(--text-primary); font-size: 18px; }}
    .project-icon-button:hover, .project-icon-button:focus {{ background: var(--bg-control-hover); border-color: var(--action); color: var(--text-primary); }}
    .project-nav-button {{ display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); background: #263238; color: var(--text-primary); font-size: 18px; font-weight: 800; line-height: 1; text-decoration: none; }}
    .project-nav-button:hover, .project-nav-button:focus {{ background: var(--bg-control-hover); border-color: var(--border-strong); }}
    .project-nav-disabled {{ opacity: .32; cursor: default; }}
    .project-nav-disabled:hover, .project-nav-disabled:focus {{ background: #555; }}
    .project-studio {{ display: grid; gap: 18px; }}
    .view-switch {{ display: inline-flex; gap: 4px; width: fit-content; padding: 4px; border: 1px solid var(--border-default); border-radius: 8px; background: var(--bg-control); }}
    .view-switch button {{ margin: 0; border-radius: 6px; background: transparent; color: var(--text-secondary); }}
    .view-switch button.active {{ background: var(--action); color: #07120f; }}
    .project-storyboard {{ display: grid; gap: 12px; }}
    .storyboard-workspace {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(360px, 520px); gap: 14px; align-items: start; }}
    .storyboard-rail {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .storyboard-card {{ position: relative; display: grid; grid-template-rows: auto 1fr; min-width: 0; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--bg-card); color: var(--text-primary); overflow: hidden; cursor: pointer; transition: border-color .15s ease, box-shadow .15s ease, transform .15s ease, background-color .15s ease; }}
    .storyboard-card-approved {{ background: linear-gradient(180deg, rgba(69,201,141,.075), rgba(69,201,141,.025)), var(--bg-card); border-color: rgba(69,201,141,.22); }}
    .storyboard-card-locked {{ cursor: not-allowed; background: linear-gradient(180deg, rgba(69,201,141,.075), rgba(69,201,141,.025)), var(--bg-card); }}
    .storyboard-card-locked > *:not(.storyboard-lock-overlay) {{ pointer-events: none; filter: grayscale(1); opacity: .52; }}
    .storyboard-lock-overlay {{ position: absolute; inset: 0; z-index: 20; display: flex; align-items: center; justify-content: center; background: rgba(11,16,18,.62); color: var(--text-primary); font-size: 12px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; backdrop-filter: grayscale(1) blur(1px); }}
    .storyboard-lock-overlay span {{ border: 1px solid rgba(255,255,255,.32); border-radius: 999px; background: rgba(8,9,13,.7); padding: 7px 11px; }}
    .storyboard-card:hover, .storyboard-card:focus {{ background: var(--bg-card-hover); border-color: var(--border-default); box-shadow: 0 0 0 3px var(--action-soft); outline: none; }}
    @property --storyboard-ring-angle {{ syntax: "<angle>"; inherits: false; initial-value: 0deg; }}
    @keyframes storyboardActiveRing {{ to {{ --storyboard-ring-angle: 360deg; }} }}
    .storyboard-card-active {{ border-color: transparent; box-shadow: 0 0 0 3px rgba(53,224,179,.18), 0 18px 48px rgba(255,79,139,.16); transform: translateY(-2px); }}
    .storyboard-card-active::before {{ --storyboard-ring-angle: 0deg; content: ""; position: absolute; inset: 0; z-index: 4; pointer-events: none; border-radius: inherit; padding: 3px; background: conic-gradient(from var(--storyboard-ring-angle), var(--studio-accent) 0 23%, transparent 23% 27%, var(--studio-pink) 27% 50%, transparent 50% 54%, var(--studio-accent) 54% 77%, transparent 77% 81%, var(--studio-pink) 81% 100%); -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); mask-composite: exclude; animation: storyboardActiveRing 2.2s linear infinite; }}
    .storyboard-card-media {{ position: relative; display: flex; align-items: center; justify-content: center; min-height: 132px; aspect-ratio: 16 / 9; background: linear-gradient(135deg, #202a2f, #12191d); color: var(--text-muted); font-weight: 700; overflow: hidden; }}
    .storyboard-card-media button {{ width: 100%; height: 100%; margin: 0; padding: 0; border: 0; border-radius: 0; background: transparent; cursor: pointer; }}
    .storyboard-card-image {{ display: block; width: 100%; height: 100%; object-fit: cover; }}
    .storyboard-card-media-clip {{ background: linear-gradient(135deg, #152024, #253238); color: #fff; }}
    .storyboard-card-video {{ display: block; width: 100%; height: 100%; object-fit: cover; background: #111; }}
    .storyboard-video-toggle {{ position: absolute; left: 8px; bottom: 8px; z-index: 2; display: inline-flex; align-items: center; justify-content: center; width: 30px !important; height: 30px !important; border-radius: 999px !important; background: rgba(11,18,20,.82) !important; color: #fff; border: 1px solid rgba(255,255,255,.2); box-shadow: 0 8px 18px rgba(0,0,0,.24); }}
    .storyboard-video-toggle:hover, .storyboard-video-toggle:focus {{ background: rgba(41,211,176,.9) !important; color: #07120f; outline: none; }}
    .storyboard-video-expand {{ position: absolute; right: 8px; bottom: 8px; z-index: 2; display: inline-flex; align-items: center; justify-content: center; width: 30px !important; height: 30px !important; border-radius: 999px !important; background: rgba(11,18,20,.82) !important; color: #fff; border: 1px solid rgba(255,255,255,.2); font-size: 15px; box-shadow: 0 8px 18px rgba(0,0,0,.24); }}
    .storyboard-video-expand:hover, .storyboard-video-expand:focus {{ background: var(--accent) !important; color: #fff; outline: none; }}
    .storyboard-play-icon {{ font-size: 0; line-height: 1; }}
    .storyboard-video-toggle[aria-label="Play clip"] .storyboard-play-icon::before {{ content: "\\25b6"; font-size: 13px; }}
    .storyboard-video-toggle[aria-label="Pause clip"] .storyboard-play-icon::before {{ content: "II"; font-size: 12px; letter-spacing: -1px; }}
    .storyboard-card-media-empty {{ padding: 14px; text-align: center; }}
    .storyboard-empty-mark {{ display: grid; gap: 4px; }}
    .storyboard-empty-mark strong {{ color: var(--text-secondary); }}
    .storyboard-empty-mark span {{ color: var(--text-muted); font-size: 12px; font-weight: 650; }}
    .storyboard-select-wrap {{ position: absolute; top: 8px; left: 8px; z-index: 5; display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; margin: 0; border: 1px solid rgba(255,255,255,.32); border-radius: 999px; background: rgba(12,18,21,.88); color: var(--text-primary); box-shadow: 0 8px 18px rgba(0,0,0,.22); cursor: pointer; }}
    .storyboard-select-wrap:has(.storyboard-select:checked) {{ background: var(--action); border-color: var(--action); color: #07120f; }}
    .storyboard-select {{ width: 18px; height: 18px; margin: 0; accent-color: var(--studio-accent); cursor: pointer; }}
    .storyboard-ok-badge {{ position: absolute; top: 8px; right: 8px; z-index: 3; pointer-events: none; display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: 1px solid rgba(69,201,141,.42); border-radius: 999px; background: rgba(219,255,238,.94); color: #167552; font-size: 23px; font-weight: 900; line-height: 1; box-shadow: 0 8px 18px rgba(0,0,0,.18); }}
    .storyboard-card-body {{ display: grid; grid-template-rows: auto auto 1fr; gap: 8px; padding: 12px; }}
    .storyboard-card-title {{ display: flex; justify-content: space-between; gap: 8px; color: var(--text-secondary); font-size: 12px; font-weight: 700; text-transform: uppercase; font-variant-numeric: tabular-nums; }}
    .storyboard-card-meta {{ display: inline-flex; align-items: center; justify-content: flex-end; gap: 6px; min-width: 0; color: var(--text-muted); }}
    .storyboard-section-badge {{ display: inline-flex; align-items: center; max-width: 86px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; border: 1px solid var(--border-default); border-radius: 999px; background: rgba(255,255,255,.035); color: var(--text-secondary); padding: 2px 6px; font-size: 10px; font-weight: 850; letter-spacing: .04em; }}
    .storyboard-section-badge-refrain {{ border-color: rgba(233,72,159,.38); background: var(--accent-soft); color: #ffd7e5; }}
    .storyboard-section-badge-verse {{ border-color: rgba(41,211,176,.32); background: var(--action-soft); color: #cdfbf1; }}
    .storyboard-section-badge-bridge {{ border-color: rgba(240,184,77,.34); background: var(--warning-soft); color: #ffe7b2; }}
    .storyboard-card-text {{ margin: 0; color: var(--text-primary); overflow-wrap: anywhere; font-size: 14px; line-height: 1.45; font-weight: 450; }}
    .storyboard-progress-strip {{ display: flex; flex-wrap: wrap; gap: 5px; }}
    .progress-step {{ border-radius: 999px; border: 1px solid var(--border-default); padding: 3px 7px; color: var(--text-muted); background: #202a2f; font-size: 10px; font-weight: 750; text-transform: uppercase; }}
    .progress-step-done {{ border-color: rgba(41,211,176,.42); background: var(--action-soft); color: #aef8e6; }}
    .segment-inspector {{ position: sticky; z-index: 70; top: 156px; display: grid; gap: 12px; min-width: 0; max-height: calc(100vh - 172px); overflow: auto; border: 1px solid var(--border-subtle); border-radius: var(--radius-lg); background: var(--bg-panel); color: var(--text-primary); padding: 14px; }}
    .segment-inspector h3 {{ margin: 0; color: var(--text-primary); }}
    .segment-inspector-nav {{ display: grid; grid-template-columns: 32px minmax(0, 1fr) 32px; gap: 10px; align-items: center; margin: -2px 0 0; }}
    .segment-inspector-title {{ color: var(--text-primary); font-size: 24px; font-weight: 800; letter-spacing: .02em; line-height: 1; text-align: center; text-transform: uppercase; }}
    .segment-nav-button {{ border: 0; padding: 0; }}
    .segment-inspector-section {{ display: grid; gap: 8px; min-width: 0; }}
    .segment-inspector-label {{ color: var(--text-muted); font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }}
    .segment-inspector-label-row {{ display: flex; justify-content: space-between; gap: 10px; align-items: center; }}
    .segment-inspector-meta {{ color: var(--text-muted); font-size: 12px; font-weight: 650; white-space: nowrap; font-variant-numeric: tabular-nums; }}
    .segment-inspector-text {{ margin: 0; overflow-wrap: anywhere; }}
    .segment-inspector-actions {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    .segment-inspector-actions .compact-form {{ width: 100%; }}
    .inspector-generation-actions {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    .inspector-generation-actions .compact-form {{ flex: 1 1 0; min-width: 0; width: auto; margin: 0; }}
    .inspector-generation-actions button {{ width: 100%; padding-left: 8px; padding-right: 8px; white-space: nowrap; }}
    .segment-inspector .storyboard-card-media {{ border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); }}
    .inspector-prompt-preview {{ display: grid; gap: 8px; align-items: start; }}
    .inspector-prompt-media-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; align-items: end; }}
    .inspector-prompt-media {{ display: grid; gap: 5px; min-width: 0; }}
    .inspector-prompt-media span {{ color: var(--text-muted); font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }}
    .inspector-prompt-media .preview-button {{ display: block; width: 100%; padding: 0; border: 0; background: transparent; }}
    .inspector-prompt-image {{ display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); background: var(--bg-control); }}
    .inspector-prompt-actions {{ display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; align-items: center; }}
    .finish-toggle {{ display: flex; width: 100%; align-items: center; justify-content: center; gap: 10px; border-radius: 8px; }}
    .finish-toggle-check {{ margin-left: auto; font-size: 23px; font-weight: 950; line-height: 1; }}
    .finish-toggle-inactive {{ background: #263238; color: #d8dfe2; border: 1px solid #3b494f; }}
    .finish-toggle-inactive:hover, .finish-toggle-inactive:focus {{ background: var(--warning-soft); color: #ffe9bc; border-color: rgba(240,184,77,.42); }}
    .finish-toggle-active {{ background: var(--success); color: #07120f; border: 1px solid var(--success); }}
    .prompt-modal.lightbox {{ z-index: 120; }}
    .image-prompt-modal-content {{ width: min(760px, 94vw); }}
    .image-prompt-modal-content .prompt-textarea {{ min-height: 144px; }}
    .segment-inspector .prompt-textarea {{ width: 100%; min-height: 76px; }}
    .project-modal-content {{ width: min(860px, 94vw); }}
    .project-modal-content form {{ margin: 0; border: 0; border-radius: 0; }}
    .project-settings-body {{ max-height: calc(88vh - 74px); overflow: auto; }}
    .project-settings-body > form {{ max-height: none; overflow: visible; }}
    @media (max-width: 980px) {{ .storyboard-workspace {{ grid-template-columns: 1fr; }} .segment-inspector {{ position: static; max-height: none; }} }}
    .project-table-view[hidden] {{ display: none; }}
    .queue-control {{ display: inline-flex; }}
    .queue-estimate {{ padding: 6px 10px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: #202a2f; color: var(--text-secondary); font-weight: 700; white-space: nowrap; cursor: pointer; }}
    .queue-modal {{ z-index: 180; }}
    .queue-modal-content {{ width: min(1120px, 96vw); height: 75vh; max-height: 75vh; display: grid; grid-template-rows: auto minmax(0, 1fr); overflow: visible; }}
    .queue-modal-body {{ min-height: 0; overflow: auto; padding-bottom: 16px; }}
    .queue-modal-content .queue-summary-grid {{ padding: 16px 16px 0; }}
    .queue-modal-content .jobs-table-wrap {{ padding-top: 16px; }}
    .danger-panel .actions {{ padding-top: 12px; }}
    .scroll-top-button {{ position: fixed; right: 18px; bottom: 18px; z-index: 30; width: 44px; height: 44px; padding: 0; display: inline-flex; align-items: center; justify-content: center; box-shadow: 0 8px 22px rgba(0,0,0,.18); }}
    table {{ width: 100%; border-collapse: collapse; background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border-subtle); }}
    th, td {{ padding: 8px; border-bottom: 1px solid var(--border-subtle); text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ background: #202a2f; color: var(--text-secondary); }}
    .status {{ font-weight: 700; }}
    .status-error {{ margin-top: 4px; color: #ffadb6; font-weight: 500; max-width: 260px; overflow-wrap: anywhere; }}
    .error {{ color: #ffadb6; max-width: 220px; overflow-wrap: anywhere; }}
    .low-confidence {{ background: var(--warning-soft); }}
    tr.section-gap {{ background: #1a2226; }}
    tr.section-verse {{ background: #1d2724; }}
    tr.section-bridge {{ background: #1a2226; }}
    tr.section-chorus {{ background: #1a2430; }}
    tr.approved-row {{ background: rgba(69,201,141,.12); box-shadow: inset 5px 0 0 var(--success); }}
    tr.low-confidence {{ box-shadow: inset 4px 0 0 var(--warning); }}
    tr.locked-row {{ position: relative; opacity: .58; pointer-events: none; }}
    .row-lock-overlay {{ position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(11,16,18,.62); color: var(--text-primary); font-weight: 800; text-transform: uppercase; letter-spacing: .04em; pointer-events: none; }}
    .confidence {{ font-weight: 700; color: var(--warning); }}
    .timing-confidence {{ margin-top: 4px; font-weight: 700; color: var(--warning); }}
    .select-cell {{ width: 44px; text-align: center; }}
    .section-legend {{ display: flex; flex-wrap: wrap; gap: 14px; align-items: center; margin: 10px 0 18px; font-size: 13px; color: var(--text-muted); }}
    .legend-swatch {{ width: 18px; height: 12px; border: 1px solid var(--border-default); display: inline-block; margin-right: 6px; vertical-align: -2px; }}
    .legend-swatch.section-gap {{ background: #1a2226; }}
    .legend-swatch.section-verse {{ background: #1d2724; }}
    .legend-swatch.section-bridge {{ background: #1a2226; }}
    .legend-swatch.section-chorus {{ background: #1a2430; }}
    .preview-image {{ width: 292px; height: 164px; object-fit: cover; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); display: block; }}
    .preview-button {{ padding: 0; border: 0; background: transparent; color: inherit; }}
    .assets-column {{ min-width: 608px; }}
    .assets-stack {{ display: grid; gap: 8px; align-content: start; }}
    .asset-previews {{ display: flex; gap: 8px; align-items: flex-start; }}
    .image-choice {{ display: grid; gap: 6px; min-width: 90px; }}
    .image-choice-inline {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }}
    .image-choice label {{ display: flex; gap: 6px; align-items: center; margin: 0; font-weight: 500; }}
    .image-choice input {{ width: auto; }}
    .asset-path {{ display: block; max-width: 140px; margin-top: 4px; color: var(--text-muted); overflow-wrap: anywhere; font-size: 11px; }}
    .lyrics-lines div + div {{ margin-top: 4px; }}
    .redo-cell {{ text-align: center; min-width: 72px; }}
    .redo-action {{ margin-top: 4px; color: var(--text-muted); font-size: 11px; overflow-wrap: anywhere; }}
    .inline-player {{ width: 180px; max-width: 100%; margin-left: 8px; vertical-align: middle; }}
    .lightbox {{ position: fixed; inset: 0; z-index: 120; display: none; align-items: center; justify-content: center; background: rgba(0,0,0,.72); backdrop-filter: blur(2px); padding: 24px; }}
    .lightbox.open {{ display: flex; }}
    .lightbox-content {{ position: relative; width: min(960px, 94vw); }}
    .lightbox video, .lightbox img {{ width: 100%; max-height: 82vh; object-fit: contain; background: #000; border-radius: 8px; }}
    .lightbox-close {{ position: absolute; top: -14px; right: -14px; z-index: 3; display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px; padding: 0; border-radius: 999px; border: 1px solid #3d4a50; background: #29343a; color: #dbe2e5; font-size: 18px; font-weight: 850; line-height: 1; box-shadow: 0 10px 24px rgba(0,0,0,.32); }}
    .lightbox-close:hover, .lightbox-close:focus {{ background: var(--accent); color: #fff; border-color: var(--accent); outline: none; }}
    .segment-inspector, .project-settings-body, .queue-modal-body, textarea {{
      scrollbar-color: #536168 #182126;
      scrollbar-width: thin;
    }}
    .segment-inspector::-webkit-scrollbar, .project-settings-body::-webkit-scrollbar, .queue-modal-body::-webkit-scrollbar, textarea::-webkit-scrollbar {{ width: 10px; height: 10px; }}
    .segment-inspector::-webkit-scrollbar-track, .project-settings-body::-webkit-scrollbar-track, .queue-modal-body::-webkit-scrollbar-track, textarea::-webkit-scrollbar-track {{ background: #182126; }}
    .segment-inspector::-webkit-scrollbar-thumb, .project-settings-body::-webkit-scrollbar-thumb, .queue-modal-body::-webkit-scrollbar-thumb, textarea::-webkit-scrollbar-thumb {{ background: #536168; border: 2px solid #182126; border-radius: 10px; }}
    .segment-inspector::-webkit-scrollbar-thumb:hover, .project-settings-body::-webkit-scrollbar-thumb:hover, .queue-modal-body::-webkit-scrollbar-thumb:hover, textarea::-webkit-scrollbar-thumb:hover {{ background: #68777f; }}
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{
        animation-duration: .01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: .01ms !important;
        scroll-behavior: auto !important;
      }}
    }}
  </style>
  <script>
    const projectRowServerHtml = new Map();
    let projectStoryboardServerHtml = '';
    function rememberProjectRows() {{
      document.querySelectorAll('tr[id^="line-row-"], tr[id^="segment-row-"]').forEach((row) => {{
        projectRowServerHtml.set(row.id, row.outerHTML);
      }});
    }}
    function rememberProjectStoryboard() {{
      const storyboard = document.getElementById('project-storyboard');
      if (!storyboard) return;
      projectStoryboardServerHtml = storyboard.outerHTML;
    }}
    function copySelectedLines(form) {{
      form.querySelectorAll('input[name="selected_lines"]').forEach((input) => input.remove());
      const selectedSegments = document.querySelectorAll('.segment-select:checked:not(:disabled)');
      const selectedLines = selectedSegments.length ? selectedSegments : document.querySelectorAll('.line-select:checked:not(:disabled)');
      if (!selectedLines.length) {{
        const hasSegments = document.querySelectorAll('.segment-select').length > 0;
        const itemLabel = hasSegments ? 'Segmente' : 'Zeilen';
        if (!confirm('Keine Checkbox markiert. Es werden alle(!) ' + itemLabel + ' verarbeitet. Fortfahren?')) {{
          return false;
        }}
      }}
      selectedLines.forEach((checkbox) => {{
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'selected_lines';
        input.value = checkbox.value;
        form.appendChild(input);
      }});
      return true;
    }}
    function currentProjectId() {{
      const match = window.location.pathname.match(/^\\/projects\\/(\\d+)/);
      return match ? Number(match[1]) : 0;
    }}
    function projectActionSubmitted(form) {{
      if (!copySelectedLines(form)) return false;
      const projectId = currentProjectId();
      if (projectId) {{
        window.setTimeout(() => refreshProjectStatus(projectId), 150);
      }}
      return true;
    }}
    function toggleRowSelection(event, row) {{
      const interactiveSelector = 'button, a, input, textarea, select, label, audio, video, img, form';
      if (event.target.closest(interactiveSelector)) return;
      const checkbox = row.querySelector('.segment-select, .line-select');
      if (!checkbox) return;
      checkbox.checked = !checkbox.checked;
    }}
    function projectRowChanged(row, replacement) {{
      const previousHtml = projectRowServerHtml.get(row.id) || row.outerHTML;
      return previousHtml !== replacement.outerHTML;
    }}
    function replaceProjectRow(row, html) {{
      const checkbox = row.querySelector('.segment-select, .line-select');
      const template = document.createElement('template');
      template.innerHTML = html.trim();
      const replacement = template.content.firstElementChild;
      if (!replacement) return;
      if (!projectRowChanged(row, replacement)) return;
      const replacementCheckbox = replacement.querySelector('.segment-select, .line-select');
      if (checkbox && replacementCheckbox) {{
        replacementCheckbox.checked = checkbox.checked;
      }}
      row.replaceWith(replacement);
      projectRowServerHtml.set(replacement.id, replacement.outerHTML);
    }}
    const projectStoryboardFieldSelector = 'input:not(.storyboard-select), textarea, select';
    function projectStoryboardHasActiveEdit(storyboard) {{
      const active = document.activeElement;
      return !!(active && active.closest && storyboard.contains(active) && active.matches(projectStoryboardFieldSelector));
    }}
    function projectStoryboardFieldDirty(field) {{
      if (field.type === 'checkbox' || field.type === 'radio') {{
        return field.checked !== field.defaultChecked;
      }}
      if (field.tagName === 'SELECT') {{
        return Array.from(field.options).some((option) => option.selected !== option.defaultSelected);
      }}
      return field.value !== field.defaultValue;
    }}
    function projectStoryboardHasDirtyFields(storyboard) {{
      return Array.from(storyboard.querySelectorAll(projectStoryboardFieldSelector)).some(projectStoryboardFieldDirty);
    }}
    function projectStoryboardHasPlayingVideo(storyboard) {{
      return Array.from(storyboard.querySelectorAll('.storyboard-card-video')).some((video) => !video.paused && !video.ended);
    }}
    function projectStoryboardHasOpenPromptModal(storyboard) {{
      return !!storyboard.querySelector('.prompt-modal.open');
    }}
    function shouldReplaceProjectStoryboard(storyboard) {{
      return !projectStoryboardHasActiveEdit(storyboard) && !projectStoryboardHasDirtyFields(storyboard) && !projectStoryboardHasPlayingVideo(storyboard) && !projectStoryboardHasOpenPromptModal(storyboard);
    }}
    function projectStoryboardChanged(storyboard, replacement) {{
      const previousHtml = projectStoryboardServerHtml || storyboard.outerHTML;
      return previousHtml !== replacement.outerHTML;
    }}
    function activeProjectStoryboardTemplateId(storyboard) {{
      const activeCard = storyboard.querySelector('.storyboard-card-active');
      return activeCard ? activeCard.dataset.inspectorTemplate : '';
    }}
    function checkedProjectStoryboardValues(storyboard) {{
      return new Set(Array.from(storyboard.querySelectorAll('.storyboard-select:checked')).map((checkbox) => checkbox.value));
    }}
    function restoreProjectStoryboardCheckedValues(storyboard, values) {{
      storyboard.querySelectorAll('.storyboard-select').forEach((checkbox) => {{
        checkbox.checked = values.has(checkbox.value);
      }});
    }}
    function restoreProjectStoryboardSelection(storyboard, templateId) {{
      if (!templateId) return;
      const card = storyboard.querySelector('[data-inspector-template="' + templateId + '"]');
      if (!card) return;
      selectStoryboardCard(storyboard, card);
    }}
    function replaceProjectStoryboard(html) {{
      const storyboard = document.getElementById('project-storyboard');
      if (!storyboard || html === undefined) return;
      if (!shouldReplaceProjectStoryboard(storyboard)) return;
      const activeTemplateId = activeProjectStoryboardTemplateId(storyboard);
      const checkedValues = checkedProjectStoryboardValues(storyboard);
      const template = document.createElement('template');
      template.innerHTML = html.trim();
      const replacement = template.content.firstElementChild;
      if (!replacement) return;
      if (!projectStoryboardChanged(storyboard, replacement)) return;
      projectStoryboardServerHtml = replacement.outerHTML;
      replacement.hidden = storyboard.hidden;
      storyboard.replaceWith(replacement);
      restoreProjectStoryboardCheckedValues(replacement, checkedValues);
      restoreProjectStoryboardSelection(replacement, activeTemplateId);
    }}
    const baseDocumentTitle = document.title.replace(/^\\(\\d+\\)\\s+/, '');
    function updateBrowserTitle(queueCount) {{
      if (queueCount === undefined || queueCount === null) return;
      const count = Math.max(0, Number(queueCount) || 0);
      document.title = count > 0 ? '(' + count + ') ' + baseDocumentTitle : baseDocumentTitle;
    }}
    function updateProjectStatus(data) {{
      updateQueueEstimate(data.queue_estimate_seconds, data.queue_count);
      updateBrowserTitle(data.queue_count);
      const progress = document.getElementById('project-progress-pill');
      if (progress && data.progress_html !== undefined) progress.outerHTML = data.progress_html;
      Object.entries(data.rows || {{}}).forEach(([rowId, html]) => {{
        const row = document.getElementById(rowId);
        if (row) replaceProjectRow(row, html);
      }});
      if (data.storyboard_html !== undefined) replaceProjectStoryboard(data.storyboard_html);
    }}
    async function refreshProjectStatus(projectId) {{
      if (!projectId) return;
      const response = await fetch('/projects/' + projectId + '/status');
      if (!response.ok) return;
      const data = await response.json();
      updateProjectStatus(data);
    }}
    async function pollProjectStatus(projectId) {{
      try {{
        await refreshProjectStatus(projectId);
      }} catch (error) {{
        return;
      }} finally {{
        window.setTimeout(() => pollProjectStatus(projectId), 2500);
      }}
    }}
    function updateJobsStatus(data) {{
      updateQueueEstimate(data.queue_estimate_seconds, data.queue_count);
      updateBrowserTitle(data.queue_count);
      const queueSummary = document.getElementById('queue-summary');
      if (queueSummary && data.queue_summary_html !== undefined) queueSummary.innerHTML = data.queue_summary_html;
      const jobsBody = document.getElementById('jobs-table-body');
      if (jobsBody && data.jobs_html !== undefined) jobsBody.innerHTML = data.jobs_html;
      const autodelete = document.querySelector('input[name="autodelete_finished"]');
      if (autodelete && data.autodelete_finished !== undefined) autodelete.checked = Boolean(data.autodelete_finished);
      const shutdown = document.querySelector('input[name="shutdown_after_queue"]');
      if (shutdown && data.shutdown_after_queue !== undefined) shutdown.checked = Boolean(data.shutdown_after_queue);
    }}
    async function refreshJobsStatus() {{
      const response = await fetch('/jobs/status');
      if (!response.ok) return;
      updateJobsStatus(await response.json());
    }}
    async function pollJobsStatus() {{
      try {{
        await refreshJobsStatus();
      }} catch (error) {{
        return;
      }} finally {{
        window.setTimeout(pollJobsStatus, 2500);
      }}
    }}
    function formatDuration(seconds) {{
      const total = Math.max(0, Math.round(Number(seconds) || 0));
      const hours = Math.floor(total / 3600);
      const minutes = Math.floor((total % 3600) / 60);
      const remaining = total % 60;
      if (hours) return hours + 'h ' + minutes + 'm';
      if (minutes) return minutes + 'm ' + remaining + 's';
      return remaining + 's';
    }}
    function queueEstimateLabel(seconds, queueCount) {{
      const count = Math.max(0, Number(queueCount) || 0);
      if (count <= 0) return 'Queue 0';
      const value = Math.max(0, Number(seconds) || 0);
      return value > 0 ? count + ' ~' + formatDuration(value) : count + ' ~?s';
    }}
    function updateQueueEstimate(seconds, queueCount) {{
      const elements = document.querySelectorAll('[data-queue-estimate="1"]');
      if (!elements.length || seconds === undefined || seconds === null) return;
      const value = Math.max(0, Number(seconds) || 0);
      const firstElement = elements[0];
      const count = queueCount === undefined || queueCount === null ? Number(firstElement.dataset.count || 0) : Math.max(0, Number(queueCount) || 0);
      elements.forEach((element) => {{
        element.dataset.seconds = String(Math.round(value));
        element.dataset.count = String(Math.round(count));
        element.textContent = queueEstimateLabel(value, count);
      }});
    }}
    function setupQueueEstimateCountdown() {{
      window.setInterval(() => {{
        const element = document.querySelector('[data-queue-estimate="1"]');
        if (!element) return;
        const value = Math.max(0, Number(element.dataset.seconds || 0) - 1);
        updateQueueEstimate(value, Number(element.dataset.count || 0));
      }}, 1000);
    }}
    function openQueueModal() {{
      const box = document.getElementById('queue-modal');
      if (!box) return;
      box.classList.add('open');
      refreshJobsStatus();
    }}
    function closeQueueModal() {{
      const box = document.getElementById('queue-modal');
      if (!box) return;
      box.classList.remove('open');
    }}
    function openNewProjectModal() {{
      const box = document.getElementById('new-project-modal');
      if (!box) return;
      box.classList.add('open');
    }}
    function closeNewProjectModal() {{
      const box = document.getElementById('new-project-modal');
      if (!box) return;
      box.classList.remove('open');
    }}
    function normalizeSearchText(value) {{
      return String(value || '').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
    }}
    function applyProjectBrowserControls() {{
      const grid = document.getElementById('project-grid');
      if (!grid) return;
      const search = normalizeSearchText(document.getElementById('project-search')?.value || '');
      const filter = document.getElementById('project-filter')?.value || 'all';
      const sort = document.getElementById('project-sort')?.value || 'newest';
      const cards = Array.from(grid.querySelectorAll('.project-card'));
      cards.sort((a, b) => {{
        if (sort === 'oldest') return Number(a.dataset.projectId || 0) - Number(b.dataset.projectId || 0);
        if (sort === 'name-asc') return String(a.dataset.title || '').localeCompare(String(b.dataset.title || ''));
        if (sort === 'name-desc') return String(b.dataset.title || '').localeCompare(String(a.dataset.title || ''));
        return Number(b.dataset.projectId || 0) - Number(a.dataset.projectId || 0);
      }}).forEach((card) => grid.appendChild(card));
      let visible = 0;
      cards.forEach((card) => {{
        const titleMatches = normalizeSearchText(card.dataset.title || '').includes(search);
        const filterMatches = filter === 'all' || card.dataset.status === filter;
        const show = titleMatches && filterMatches;
        card.classList.toggle('project-card-hidden', !show);
        if (show) visible += 1;
      }});
      const empty = document.getElementById('project-empty-state');
      if (empty) empty.classList.toggle('visible', visible === 0);
    }}
    function setupProjectBrowserControls() {{
      ['project-search', 'project-filter', 'project-sort'].forEach((id) => {{
        const element = document.getElementById(id);
        if (!element) return;
        element.addEventListener('input', applyProjectBrowserControls);
        element.addEventListener('change', applyProjectBrowserControls);
      }});
      document.querySelectorAll('.project-card video').forEach((video) => {{
        const card = video.closest('.project-card');
        if (!card) return;
        card.addEventListener('mouseenter', () => {{
          video.muted = true;
          video.play().catch(() => {{}});
        }});
        card.addEventListener('mouseleave', () => {{
          video.pause();
          video.currentTime = 0;
        }});
      }});
      applyProjectBrowserControls();
    }}
    function openProjectSettingsModal() {{
      const box = document.getElementById('project-settings-modal');
      if (!box) return;
      box.classList.add('open');
    }}
    function closeProjectSettingsModal() {{
      const box = document.getElementById('project-settings-modal');
      if (!box) return;
      box.classList.remove('open');
    }}
    function openPromptModal(id) {{
      const box = document.getElementById(id);
      if (!box) return;
      box.classList.add('open');
    }}
    function closePromptModal(id) {{
      const box = document.getElementById(id);
      if (!box) return;
      box.classList.remove('open');
    }}
    function scrollToTop() {{
      const firstSegment = document.querySelector('tr[id^="segment-row-"]');
      const target = firstSegment || document.querySelector('tr[id^="line-row-"]');
      if (!target) {{
        window.scrollTo({{ top: 0, behavior: 'smooth' }});
        return;
      }}
      const topbar = document.querySelector('.project-topbar');
      const offset = topbar ? topbar.getBoundingClientRect().height : 0;
      const top = target.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo({{ top: Math.max(0, top), behavior: 'smooth' }});
    }}
    function switchProjectView(view) {{
      const storyboard = document.getElementById('project-storyboard');
      const table = document.getElementById('project-table-view');
      if (!storyboard || !table) return;
      const showTable = view === 'table';
      storyboard.hidden = showTable;
      table.hidden = !showTable;
      document.querySelectorAll('[data-project-view]').forEach((button) => {{
        const active = button.dataset.projectView === view;
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
      }});
    }}
    function selectStoryboardCard(storyboard, card) {{
      const templateId = card.dataset.inspectorTemplate;
      const template = templateId ? document.getElementById(templateId) : null;
      const current = storyboard.querySelector('#segment-inspector');
      if (!template || !current) return;
      storyboard.querySelectorAll('.storyboard-card-active').forEach((item) => item.classList.remove('storyboard-card-active'));
      card.classList.add('storyboard-card-active');
      const fragment = template.content.cloneNode(true);
      const replacement = fragment.querySelector('#segment-inspector');
      if (!replacement) return;
      current.replaceWith(replacement);
    }}
    function selectStoryboardTemplate(templateId) {{
      const storyboard = document.getElementById('project-storyboard');
      if (!storyboard || !templateId) return;
      const card = storyboard.querySelector('[data-inspector-template="' + templateId + '"]');
      if (!card) return;
      selectStoryboardCard(storyboard, card);
    }}
    function selectStoryboardItem(event, card) {{
      const interactiveSelector = 'button, a, input, textarea, select, label, audio, video, img, form';
      if (event && event.target && event.target.closest(interactiveSelector)) return;
      if (card.dataset.locked === '1') return;
      const storyboard = card.closest('#project-storyboard');
      if (!storyboard) return;
      selectStoryboardCard(storyboard, card);
    }}
    function scrollStorageKey() {{
      return 'musicvideogen-scroll:' + window.location.pathname;
    }}
    function storyboardSelectionStorageKey() {{
      return 'musicvideogen-storyboard-selection:' + window.location.pathname;
    }}
    function rememberProjectStoryboardSelection() {{
      const storyboard = document.getElementById('project-storyboard');
      if (!storyboard) return;
      const activeTemplateId = activeProjectStoryboardTemplateId(storyboard);
      if (!activeTemplateId) return;
      sessionStorage.setItem(storyboardSelectionStorageKey(), activeTemplateId);
    }}
    function rememberScrollPosition() {{
      rememberProjectStoryboardSelection();
      sessionStorage.setItem(scrollStorageKey(), String(window.scrollY));
    }}
    function openQueueJobRow(row) {{
      const href = row.dataset.href;
      if (!href) return;
      const templateId = row.dataset.templateId || '';
      if (templateId) {{
        sessionStorage.setItem('musicvideogen-storyboard-selection:' + href, templateId);
      }}
      window.location.href = href;
    }}
    function confirmProjectSettingsSave(form) {{
      rememberScrollPosition();
      return true;
    }}
    document.addEventListener('submit', rememberScrollPosition);
    document.addEventListener('DOMContentLoaded', () => {{
      rememberProjectRows();
      rememberProjectStoryboard();
      setupProjectBrowserControls();
      const storyboard = document.getElementById('project-storyboard');
      const storedStoryboardTemplate = sessionStorage.getItem(storyboardSelectionStorageKey());
      if (storyboard && storedStoryboardTemplate) {{
        restoreProjectStoryboardSelection(storyboard, storedStoryboardTemplate);
      }}
      const stored = sessionStorage.getItem(scrollStorageKey());
      if (stored === null) return;
      const scrollY = Number(stored);
      if (!Number.isFinite(scrollY)) return;
      requestAnimationFrame(() => window.scrollTo(0, scrollY));
    }});
    function toggleAudio(button) {{
      const audio = button.nextElementSibling;
      if (!audio) return;
      if (audio.paused) {{
        audio.play();
        button.textContent = '||';
      }} else {{
        audio.pause();
        button.textContent = '▶';
      }}
      audio.onended = () => {{ button.textContent = '▶'; }};
    }}
    function toggleStoryboardVideo(event, target) {{
      if (event) event.stopPropagation();
      const media = target.closest('.storyboard-card-media-clip');
      if (!media) return;
      const video = media.querySelector('video');
      const button = media.querySelector('.storyboard-video-toggle');
      if (!video) return;
      if (video.paused) {{
        video.play();
        if (button) {{
          button.setAttribute('aria-label', 'Pause clip');
          button.querySelector('.storyboard-play-icon').textContent = 'Ⅱ';
        }}
      }} else {{
        video.pause();
        if (button) {{
          button.setAttribute('aria-label', 'Play clip');
          button.querySelector('.storyboard-play-icon').textContent = '▶';
        }}
      }}
      video.onended = () => {{
        if (!button) return;
        button.setAttribute('aria-label', 'Play clip');
        button.querySelector('.storyboard-play-icon').textContent = '▶';
      }};
    }}
    function resetStoryboardVideo(target) {{
      const media = target && target.closest ? target.closest('.storyboard-card-media-clip') : null;
      if (!media) return;
      const video = media.querySelector('video');
      const button = media.querySelector('.storyboard-video-toggle');
      if (video) {{
        video.pause();
        video.currentTime = 0;
      }}
      if (button) {{
        button.setAttribute('aria-label', 'Play clip');
        button.querySelector('.storyboard-play-icon').textContent = '▶';
      }}
    }}
    function openClipLightbox(src, source) {{
      resetStoryboardVideo(source);
      const box = document.getElementById('clip-lightbox');
      const video = document.getElementById('clip-lightbox-video');
      video.src = src;
      box.classList.add('open');
      video.play();
    }}
    function closeClipLightbox() {{
      const box = document.getElementById('clip-lightbox');
      const video = document.getElementById('clip-lightbox-video');
      video.pause();
      video.removeAttribute('src');
      video.load();
      box.classList.remove('open');
    }}
    function openImageLightbox(src) {{
      const box = document.getElementById('image-lightbox');
      const image = document.getElementById('image-lightbox-image');
      image.src = src;
      box.classList.add('open');
    }}
    function closeImageLightbox() {{
      const box = document.getElementById('image-lightbox');
      const image = document.getElementById('image-lightbox-image');
      image.removeAttribute('src');
      box.classList.remove('open');
    }}
  </script>
</head>
<body><main>{body}</main></body>
</html>"""


def _browser_title(title: str, queue_count: int = 0) -> str:
    count = max(0, int(queue_count or 0))
    return f"({count}) {title}" if count else title

__all__ = ["_page", "_browser_title"]
