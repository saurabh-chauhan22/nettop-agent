<script>
  import { onMount, tick } from 'svelte';
  // Per-icon imports: the package root would make Vite compile all 1,800+ icons
  import Activity from '@lucide/svelte/icons/activity';
  import ArrowUp from '@lucide/svelte/icons/arrow-up';
  import Check from '@lucide/svelte/icons/check';
  import Database from '@lucide/svelte/icons/database';
  import Download from '@lucide/svelte/icons/download';
  import ListOrdered from '@lucide/svelte/icons/list-ordered';
  import MessageSquare from '@lucide/svelte/icons/message-square';
  import PanelLeft from '@lucide/svelte/icons/panel-left';
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import X from '@lucide/svelte/icons/x';
  import Trace from './Trace.svelte';

  // Plain-language names for the agent's labels
  const LABELS = {
    rf_impairment: 'RF impairment',
    dhcp_storm: 'DHCP storm',
    interface_flap: 'Interface flapping',
    unknown: 'Unknown cause',
    escalate_field_tech: 'Escalate to a field tech',
    dhcp_discard_clear: 'Clear DHCP discards',
    interface_reset: 'Reset the interface',
    none: 'No action',
  };
  const SIGNALS = {
    snr_drop: 'SNR drop',
    tx_power_spike: 'transmit power spike',
    errors: 'errors',
    dhcp_discover_burst: 'DHCP DISCOVER burst',
    link_down: 'link down',
  };

  const SEVERITY_TONE = { 'RF signal loss': 'fault', 'Link loss': 'caution' };

  let anomalies = $state(null); // null until the first load from the lake finishes
  let audit = $state([]);
  let conversations = $state([]);
  let messages = $state([]);
  let pending = $state(null);
  let draft = $state('');
  let busy = $state(false);
  let loadError = $state('');
  let chatError = $state('');
  let activeDevice = $state('');
  let sidebarOpen = $state(true);
  let threadId = $state(crypto.randomUUID());
  let log = $state(null);

  // Starter shortcuts point at real anomalies: one RF fault, one remotely fixable fault
  let rfDevice = $derived(anomalies?.find((a) => a.signals.includes('snr_drop'))?.device_id);
  let fixableDevice = $derived(anomalies?.find((a) => !a.signals.includes('snr_drop'))?.device_id);

  async function getJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${url} returned ${res.status}`);
    return res.json();
  }

  async function refresh() {
    try {
      [anomalies, audit, conversations] = await Promise.all([
        getJSON('/api/anomalies'), getJSON('/api/audit'), getJSON('/api/conversations'),
      ]);
      loadError = '';
    } catch (e) {
      loadError = `Could not load anomalies (${e.message}). Start the API with python ui/api.py, then reload.`;
    }
  }

  async function send(text) {
    text = text.trim();
    if (!text || busy) return;
    messages.push({ role: 'you', text });
    draft = '';
    busy = true;
    chatError = '';
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: threadId, message: text }),
      });
      const reply = await res.json();
      if (!res.ok) throw new Error(reply.error ?? `status ${res.status}`);
      messages.push({ role: 'agent', text: reply.text, card: reply.card });
      pending = reply.pending;
      if (reply.card.kind === 'diagnosis') activeDevice = reply.card.device_id;
      conversations = await getJSON('/api/conversations');
      if (reply.card.kind === 'action') audit = await getJSON('/api/audit');
    } catch (e) {
      chatError = `The agent did not answer: ${e.message}. Your message is kept above; try sending it again.`;
    } finally {
      busy = false;
    }
  }

  function investigate(device) {
    if (!device) return;
    activeDevice = device;
    send(`What's wrong with ${device}?`);
  }

  async function openConversation(id) {
    if (busy || id === threadId) return;
    try {
      const saved = await getJSON(`/api/conversations/${encodeURIComponent(id)}`);
      threadId = id;
      messages = saved.messages;
      pending = saved.pending;
      activeDevice = saved.messages.findLast((m) => m.card?.kind === 'diagnosis')?.card.device_id ?? '';
      chatError = '';
    } catch (e) {
      chatError = `Could not open that conversation (${e.message}).`;
    }
  }

  function newConversation() {
    threadId = crypto.randomUUID();
    messages = [];
    pending = null;
    activeDevice = '';
    chatError = '';
  }

  function exportConversation() {
    const body = messages.map((m) => (m.role === 'you' ? `**You:** ${m.text}` : m.text)).join('\n\n');
    const url = URL.createObjectURL(new Blob([`# AgentNet conversation\n\n${body}\n`], { type: 'text/markdown' }));
    Object.assign(document.createElement('a'), { href: url, download: 'agentnet-conversation.md' }).click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function onComposerKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send(draft);
    }
  }

  // audit.log line: "<ISO time> <action> <device> (simulated)"
  const parseAudit = (line) => {
    const [stamp, action, device] = line.split(' ');
    return { stamp, action, device };
  };
  const sentence = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  const day = (iso) => new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric' });
  const time = (iso) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  const tone = (action) => (action === 'escalate_field_tech' ? 'fault' : action === 'none' ? 'quiet' : 'caution');

  onMount(refresh);

  $effect(() => {
    messages.length;
    busy;
    tick().then(() => log?.scrollTo({ top: log.scrollHeight, behavior: 'smooth' }));
  });
</script>

<div class="app" class:collapsed={!sidebarOpen}>
  {#if sidebarOpen}
    <aside class="sidebar">
      <div class="brand">
        <span class="logo" aria-hidden="true"><Activity size={15} /></span>
        <span class="brand-name">AgentNet</span>
        <button class="icon-btn" onclick={() => (sidebarOpen = false)} aria-label="Hide sidebar">
          <PanelLeft size={16} />
        </button>
      </div>

      <button class="new-chat" onclick={newConversation} disabled={busy}>
        <SquarePen size={15} /> New conversation
      </button>

      <nav aria-labelledby="history-heading">
        <h2 id="history-heading" class="section-label">Conversations</h2>
        {#if conversations.length}
          <ul class="history">
            {#each conversations as c (c.id)}
              <li>
                <button class="history-item" class:active={c.id === threadId} aria-current={c.id === threadId}
                        onclick={() => openConversation(c.id)} disabled={busy}
                        title="{c.title} ({day(c.updated_at)}, {time(c.updated_at)})">
                  <MessageSquare size={14} />
                  <span class="history-title">{c.title}</span>
                </button>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="small muted pad">Your conversations appear here.</p>
        {/if}
      </nav>

      <nav aria-labelledby="anomalies-heading">
        <h2 id="anomalies-heading" class="section-label">
          Anomalies {#if anomalies}<span class="count">{anomalies.length}</span>{/if}
        </h2>
        {#if loadError}
          <p class="error small" role="alert">{loadError}</p>
        {:else if !anomalies}
          <p class="small muted pulse">Reading the data lake</p>
        {:else if !anomalies.length}
          <p class="small muted">No anomalies in the last 24 hours.</p>
        {/if}
        <ul class="anomalies">
          {#each anomalies ?? [] as a (a.device_id)}
            <li>
              <button class="anomaly" class:active={a.device_id === activeDevice} aria-current={a.device_id === activeDevice}
                      onclick={() => investigate(a.device_id)} disabled={busy}
                      title="Investigate {a.device_id}">
                <span class="anomaly-row">
                  <span class="device">{a.device_id}</span>
                  <span class="window">{time(a.start)} to {time(a.end)}</span>
                </span>
                <Trace snr={a.snr} ts={a.ts} start={a.start} end={a.end} />
                <span class="signals">{sentence(a.signals.map((s) => SIGNALS[s] ?? s).join(', '))}</span>
              </button>
            </li>
          {/each}
        </ul>
      </nav>

      <section aria-labelledby="audit-heading">
        <h2 id="audit-heading" class="section-label">Actions taken</h2>
        {#if audit.length}
          <ul class="audit">
            {#each audit.map(parseAudit) as entry}
              <li>
                <span class="when">{day(entry.stamp)}, {time(entry.stamp)}</span>
                {LABELS[entry.action] ?? entry.action} on <span class="nowrap">{entry.device}</span>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="small muted">Nothing yet. Actions you approve are logged here.</p>
        {/if}
      </section>

      <div class="note">
        <span class="note-icon" aria-hidden="true"><ShieldCheck size={16} /></span>
        <p class="note-title">Approval required</p>
        <p class="small muted">Remote actions run only after you approve them. RF faults go to a field tech.</p>
      </div>
    </aside>
  {/if}

  <main class="panel">
    <div class="topbar">
      <div class="topbar-left">
        {#if !sidebarOpen}
          <button class="icon-btn" onclick={() => (sidebarOpen = true)} aria-label="Show sidebar"><PanelLeft size={16} /></button>
        {/if}
        <span class="pill"><Sparkles size={13} /> claude-opus-5</span>
      </div>
      <button class="pill" onclick={exportConversation} disabled={!messages.length}>
        Export <Download size={13} />
      </button>
    </div>

    {#if !messages.length}
      <div class="hero">
        <div class="orb" aria-hidden="true"><span class="orb-surface"></span></div>
        <h1>What should we look into?</h1>
        <p class="muted">Investigate an anomaly, ask the network data a question, or approve a fix.</p>
      </div>
    {:else}
      <div class="log" bind:this={log} aria-live="polite">
        <div class="thread">
          {#each messages as m}
            {#if m.role === 'you'}
              <p class="bubble">{m.text}</p>
            {:else}
              <div class="agent">
                <span class="mini-orb" aria-hidden="true"><span class="orb-surface"></span></span>
                <div class="agent-body">
                  {#if m.card?.kind === 'diagnosis'}
                    <article class="finding">
                      <div class="finding-head">
                        <h3>{m.card.device_id}: {LABELS[m.card.root_cause] ?? m.card.root_cause}</h3>
                        <span class="chip {tone(m.card.action)}">{LABELS[m.card.action] ?? m.card.action}</span>
                      </div>
                      <ul class="evidence">{#each m.card.evidence as fact}<li>{fact}</li>{/each}</ul>
                    </article>
                  {:else if m.card?.kind === 'triage'}
                    <article class="finding">
                      <h3>{m.card.items.length} modems flagged, most urgent first</h3>
                      <ol class="triage">
                        {#each m.card.items as item}
                          <li>
                            <span class="device">{item.device_id}</span>
                            <span class="chip {SEVERITY_TONE[item.severity] ?? 'quiet'}">{item.severity}</span>
                            <span class="small muted triage-window">{time(item.start)} to {time(item.end)}</span>
                            <button class="pill" onclick={() => investigate(item.device_id)} disabled={busy}>Investigate</button>
                          </li>
                        {/each}
                      </ol>
                      <p class="small muted">{m.card.rule}</p>
                    </article>
                  {:else if m.card?.kind === 'sql'}
                    <p>{m.card.answer}</p>
                    <p class="small muted sql-label"><Database size={12} /> Query run against the data lake</p>
                    <pre><code>{m.card.sql}</code></pre>
                  {:else if m.card?.kind === 'action'}
                    <p class="outcome" class:skipped={!m.card.approved}>
                      {#if m.card.approved}<Check size={15} />{:else}<X size={15} />{/if}
                      {m.card.approved
                        ? `Done: ${LABELS[m.card.action] ?? m.card.action} on ${m.card.device_id}. Simulated and added to the action log.`
                        : `Skipped: ${LABELS[m.card.action] ?? m.card.action} on ${m.card.device_id}. Nothing was run.`}
                    </p>
                  {:else}
                    <p>{m.text}</p>
                  {/if}
                </div>
              </div>
            {/if}
          {/each}
          {#if busy}
            <div class="agent">
              <span class="mini-orb thinking" aria-hidden="true"><span class="orb-surface"></span></span>
              <p class="muted pulse">Working on it</p>
            </div>
          {/if}
        </div>
      </div>
    {/if}

    <div class="dock">
      {#if pending}
        <div class="approval" role="group" aria-labelledby="approval-heading">
          <span class="approval-icon" aria-hidden="true"><ShieldCheck size={18} /></span>
          <div class="approval-text">
            <h2 id="approval-heading">{LABELS[pending.action] ?? pending.action} on {pending.device_id}?</h2>
            <p class="small muted">Runs a remote command on the device. Simulated in this demo and written to the action log.</p>
          </div>
          <div class="choices">
            <button class="btn-primary" onclick={() => send('yes')} disabled={busy}>Approve</button>
            <button class="btn-ghost" onclick={() => send('no')} disabled={busy}>Reject</button>
          </div>
        </div>
      {/if}

      {#if chatError}<p class="error small" role="alert">{chatError}</p>{/if}

      {#if !messages.length}
        <div class="quick">
          <button class="pill" onclick={() => investigate(rfDevice)} disabled={busy || !rfDevice}>
            <Activity size={13} /> Investigate {rfDevice ?? 'an anomaly'}
          </button>
          <button class="pill" onclick={() => send('Which modem had the lowest SNR reading?')} disabled={busy}>
            <Database size={13} /> Lowest SNR reading
          </button>
          <button class="pill" onclick={() => send('What needs attention first?')} disabled={busy}>
            <ListOrdered size={13} /> What needs attention first?
          </button>
        </div>
      {/if}

      <form class="composer" onsubmit={(e) => { e.preventDefault(); send(draft); }}>
        <div class="composer-input">
          <span class="spark" aria-hidden="true"><Sparkles size={16} /></span>
          <label for="ask" class="sr-only">Ask about a modem or the network data</label>
          <textarea id="ask" rows="2" bind:value={draft} onkeydown={onComposerKey} disabled={busy}
                    placeholder="Ask about a modem or the network data"></textarea>
        </div>
        <div class="composer-bar">
          <span class="hint"><Database size={13} /> Read-only access to the data lake</span>
          <button type="submit" class="send" disabled={busy || !draft.trim()} aria-label="Send">
            <ArrowUp size={16} />
          </button>
        </div>
      </form>

      {#if !messages.length}
        <div class="tiles">
          <button class="tile" onclick={() => investigate(rfDevice)} disabled={busy || !rfDevice}>
            <span class="tile-top"><span class="tile-icon"><Activity size={15} /></span><span class="chip quiet">Investigate</span></span>
            <span class="tile-title">Investigation agent</span>
            <span class="tile-text">Diagnose a flagged modem from its telemetry, logs, and DHCP activity.</span>
          </button>
          <button class="tile" onclick={() => send('How many cable modems are on CMTS-WEST-01?')} disabled={busy}>
            <span class="tile-top"><span class="tile-icon"><Database size={15} /></span><span class="chip quiet">Ask the data</span></span>
            <span class="tile-title">Data lake questions</span>
            <span class="tile-text">Ask in plain English and see the SQL that answered it.</span>
          </button>
          <button class="tile" onclick={() => investigate(fixableDevice)} disabled={busy || !fixableDevice}>
            <span class="tile-top"><span class="tile-icon"><ShieldCheck size={15} /></span><span class="chip quiet">Approve a fix</span></span>
            <span class="tile-title">Guarded remediation</span>
            <span class="tile-text">Remote fixes wait for your approval before anything runs.</span>
          </button>
        </div>
      {/if}
    </div>
  </main>
</div>

<style>
  .app {
    display: grid;
    grid-template-columns: 17.5rem minmax(0, 1fr);
    gap: 0.5rem;
    height: 100dvh;
    padding: 0.5rem;
    background: var(--black);
  }
  .app.collapsed { grid-template-columns: minmax(0, 1fr); }

  /* Sidebar */
  .sidebar {
    display: flex;
    flex-direction: column;
    gap: 1.1rem;
    padding: 0.6rem 0.4rem 0.4rem;
    overflow-y: auto;
    min-height: 0;
  }
  .brand { display: flex; align-items: center; gap: 0.6rem; padding: 0 0.35rem; }
  .logo {
    display: grid;
    place-items: center;
    width: 1.9rem;
    height: 1.9rem;
    border-radius: 50%;
    background: var(--text);
    color: var(--black);
  }
  .brand-name { font-weight: 600; font-size: 1.05rem; flex: 1; }
  .icon-btn {
    display: grid;
    place-items: center;
    width: 1.9rem;
    height: 1.9rem;
    border-radius: 8px;
    color: var(--muted);
  }
  .icon-btn:hover { background: var(--surface-2); color: var(--text); }
  .new-chat {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.6rem 0.75rem;
    border-radius: 10px;
    background: var(--surface-2);
    border: 1px solid var(--line);
  }
  .new-chat:hover:not(:disabled) { background: rgba(255, 255, 255, 0.12); }

  .section-label {
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--muted);
    padding: 0 0.35rem;
    margin-bottom: 0.4rem;
  }
  .count { color: var(--fault); font-variant-numeric: tabular-nums; margin-left: 0.2rem; }
  .small { font-size: 0.8125rem; }
  .muted { color: var(--muted); }

  .pad { padding: 0 0.35rem; }
  .history {
    list-style: none;
    padding: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr); /* lets long titles truncate instead of widening the list */
    gap: 0.1rem;
    max-height: 11.5rem;
    overflow-y: auto;
  }
  .history-item {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.45rem 0.6rem;
    border-radius: 8px;
    color: var(--muted);
    font-weight: 400;
    text-align: left;
  }
  .history-item:hover:not(:disabled) { background: var(--surface); color: var(--text); }
  .history-item.active { background: var(--surface-2); color: var(--text); }
  .history-item:disabled { opacity: 1; }
  .history-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }

  .anomalies { list-style: none; padding: 0; display: grid; gap: 0.15rem; }
  .anomaly {
    width: 100%;
    display: grid;
    gap: 0.3rem;
    padding: 0.55rem 0.6rem;
    border-radius: 10px;
    text-align: left;
    --trace-height: 1.6rem;
  }
  .anomaly:hover:not(:disabled) { background: var(--surface); }
  .anomaly.active { background: var(--surface-2); box-shadow: inset 2px 0 0 var(--accent-soft); }
  .anomaly:disabled { opacity: 1; }
  .anomaly-row { display: flex; justify-content: space-between; align-items: baseline; gap: 0.5rem; }
  .device { font-weight: 600; font-size: 0.875rem; font-variant-numeric: tabular-nums; }
  .window, .signals { font-size: 0.75rem; color: var(--muted); font-weight: 400; }

  .audit { list-style: none; padding: 0 0.35rem; display: grid; gap: 0.4rem; font-size: 0.8125rem; }
  .when { color: var(--muted); font-variant-numeric: tabular-nums; margin-right: 0.3rem; }
  .nowrap { white-space: nowrap; }

  .note {
    margin-top: auto;
    display: grid;
    justify-items: center;
    text-align: center;
    gap: 0.35rem;
    padding: 1rem 0.9rem;
    border-radius: 14px;
    background: var(--surface);
    border: 1px solid var(--line);
  }
  .note-icon {
    display: grid;
    place-items: center;
    width: 2rem;
    height: 2rem;
    border-radius: 50%;
    background: var(--surface-2);
    color: var(--accent-soft);
  }
  .note-title { font-weight: 600; font-size: 0.875rem; }

  /* Main panel */
  .panel {
    position: relative;
    display: grid;
    grid-template-rows: auto minmax(0, 1fr) auto;
    min-height: 0;
    border-radius: 18px;
    border: 1px solid var(--line);
    overflow: hidden;
    background:
      radial-gradient(ellipse 75% 55% at 60% -5%, rgba(128, 60, 160, 0.55), transparent 70%),
      radial-gradient(ellipse 50% 40% at 100% 30%, rgba(90, 40, 120, 0.25), transparent 70%),
      linear-gradient(180deg, #1b1520, var(--panel) 60%);
  }
  .topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.9rem 1.2rem;
  }
  .topbar-left { display: flex; align-items: center; gap: 0.5rem; }
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 0.8rem;
    border-radius: 999px;
    background: rgba(0, 0, 0, 0.4);
    border: 1px solid var(--line);
    font-size: 0.8125rem;
  }
  button.pill:hover:not(:disabled) { border-color: var(--line-strong); background: rgba(0, 0, 0, 0.55); }

  .hero {
    align-self: center;
    display: grid;
    justify-items: center;
    text-align: center;
    gap: 0.9rem;
    padding: 1rem;
  }
  .hero h1 { font-size: 1.75rem; font-weight: 500; letter-spacing: -0.01em; }

  /* One load sequence: orb, headline, subtitle rise in, in that order */
  .hero > * { animation: rise 0.7s cubic-bezier(0.2, 0.7, 0.2, 1) both; }
  .hero > h1 { animation-delay: 0.12s; }
  .hero > p { animation-delay: 0.22s; }
  @keyframes rise { from { opacity: 0; transform: translateY(10px); } }

  /* The sphere: a color band spins under fixed lighting, which reads as the surface rotating */
  .orb {
    position: relative;
    width: 3.75rem;
    height: 3.75rem;
    border-radius: 50%;
    overflow: hidden;
    isolation: isolate;
    margin-bottom: 0.4rem;
    background: #2a1257;
    animation:
      rise 0.7s cubic-bezier(0.2, 0.7, 0.2, 1) both,
      float 6s ease-in-out 0.7s infinite,
      breathe 4s ease-in-out infinite;
  }
  .orb-surface {
    position: absolute;
    inset: -30%;
    background: conic-gradient(from 0deg, #7b3fe4, #3d6dff, #c48cff, #4a1f8f, #e0b8ff, #5b2bd6, #7b3fe4);
    filter: blur(5px);
    animation: spin 9s linear infinite;
  }
  .orb::after,
  .mini-orb::after {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 50%;
    /* fixed light from the upper left, plus darker edges for depth */
    background:
      radial-gradient(circle at 33% 27%, rgba(255, 244, 255, 0.95) 0%, rgba(230, 196, 255, 0.5) 14%, transparent 36%),
      radial-gradient(circle at 50% 50%, transparent 52%, rgba(10, 0, 30, 0.7) 100%);
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes float { 50% { transform: translateY(-5px); } }
  @keyframes breathe {
    0%, 100% { box-shadow: 0 0 38px rgba(163, 92, 240, 0.45); }
    50% { box-shadow: 0 0 62px rgba(163, 92, 240, 0.75); }
  }

  /* Conversation */
  .log { overflow-y: auto; min-height: 0; scroll-behavior: smooth; }
  .thread {
    width: min(100%, 50rem);
    margin: 0 auto;
    padding: 0.5rem 1.5rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }
  .bubble {
    align-self: flex-end;
    max-width: 75%;
    padding: 0.6rem 0.95rem;
    border-radius: 16px 16px 4px 16px;
    background: var(--surface-2);
    border: 1px solid var(--line);
  }
  .agent { display: flex; gap: 0.75rem; align-items: flex-start; }
  .agent-body { display: grid; gap: 0.5rem; min-width: 0; flex: 1; }
  /* Same sphere as the hero orb: still at rest, spinning fast while the agent works */
  .mini-orb {
    position: relative;
    flex-shrink: 0;
    width: 1.5rem;
    height: 1.5rem;
    border-radius: 50%;
    margin-top: 0.1rem;
    overflow: hidden;
    isolation: isolate;
    background: #2a1257;
    box-shadow: 0 0 14px rgba(163, 92, 240, 0.45);
  }
  .mini-orb .orb-surface { filter: blur(2px); animation: none; }
  .mini-orb.thinking { animation: glow 1.4s ease-in-out infinite; }
  .mini-orb.thinking .orb-surface { animation: spin 1.4s linear infinite; }
  @keyframes glow { 50% { box-shadow: 0 0 26px rgba(207, 168, 255, 0.85); } }
  .pulse { animation: fade 1.4s ease-in-out infinite; }
  @keyframes fade { 50% { opacity: 0.4; } }

  .finding {
    display: grid;
    gap: 0.6rem;
    padding: 0.9rem 1rem;
    border-radius: 14px;
    background: rgba(10, 8, 12, 0.55);
    border: 1px solid var(--line);
  }
  .finding-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.75rem; }
  .finding h3 { font-size: 1rem; font-weight: 600; }
  .evidence { padding-left: 1.1rem; display: grid; gap: 0.25rem; color: #d9d3e2; }
  .chip {
    flex-shrink: 0;
    font-size: 0.75rem;
    font-weight: 500;
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    border: 1px solid var(--line);
    background: var(--surface-2);
    white-space: nowrap;
  }
  .chip.fault { color: var(--fault); border-color: rgba(242, 109, 130, 0.35); background: rgba(242, 109, 130, 0.1); }
  .chip.caution { color: var(--caution); border-color: rgba(240, 179, 90, 0.35); background: rgba(240, 179, 90, 0.1); }
  .chip.quiet { color: var(--muted); }
  .triage { padding-left: 1.3rem; display: grid; gap: 0.45rem; }
  .triage li { padding-left: 0.2rem; }
  .triage li > * { vertical-align: middle; }
  .triage .device { display: inline-block; min-width: 6.5rem; }
  .triage .chip { margin-right: 0.5rem; }
  .triage-window { margin-right: 0.6rem; font-variant-numeric: tabular-nums; }
  .triage .pill { padding: 0.2rem 0.65rem; font-size: 0.75rem; }
  .sql-label { display: flex; align-items: center; gap: 0.35rem; }
  pre {
    padding: 0.7rem 0.9rem;
    border-radius: 10px;
    background: rgba(0, 0, 0, 0.45);
    border: 1px solid var(--line);
    font: 0.8125rem/1.55 var(--code);
    color: #e3d7f5;
    white-space: pre-wrap;
    overflow-x: auto;
  }
  .outcome { display: flex; gap: 0.45rem; align-items: flex-start; color: #9fe3c6; }
  .outcome.skipped { color: var(--muted); }

  /* Dock: approval, starters, composer */
  .dock {
    width: min(100%, 50rem);
    margin: 0 auto;
    padding: 0 1.5rem 1.25rem;
    display: grid;
    gap: 0.75rem;
  }
  .approval {
    display: flex;
    align-items: center;
    gap: 0.85rem;
    padding: 0.85rem 1rem;
    border-radius: 14px;
    background: rgba(163, 92, 240, 0.12);
    border: 1px solid rgba(207, 168, 255, 0.35);
    box-shadow: 0 0 30px rgba(163, 92, 240, 0.15);
  }
  .approval-icon { color: var(--accent-soft); display: grid; }
  .approval-text { flex: 1; display: grid; gap: 0.15rem; }
  .approval h2 { font-size: 0.9375rem; font-weight: 600; }
  .choices { display: flex; gap: 0.5rem; flex-shrink: 0; }
  .btn-primary, .btn-ghost { padding: 0.5rem 1rem; border-radius: 999px; }
  .btn-primary { background: linear-gradient(135deg, #b672ff, #7c3ae0); color: #fff; }
  .btn-ghost { border: 1px solid var(--line-strong); }

  .quick { display: flex; flex-wrap: wrap; gap: 0.5rem; }

  .composer {
    display: grid;
    gap: 0.4rem;
    padding: 0.8rem 0.9rem 0.6rem;
    border-radius: 16px;
    background: rgba(18, 14, 22, 0.8);
    border: 1px solid var(--line-strong);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
  }
  .composer:focus-within { border-color: rgba(207, 168, 255, 0.55); }
  .composer-input { display: flex; gap: 0.6rem; align-items: flex-start; }
  .spark { color: var(--accent-soft); display: grid; margin-top: 0.2rem; }
  textarea {
    flex: 1;
    resize: none;
    border: 0;
    outline: none;
    background: transparent;
    color: var(--text);
    font: 400 0.9375rem/1.5 var(--body);
  }
  textarea::placeholder { color: var(--muted); }
  .composer-bar { display: flex; justify-content: space-between; align-items: center; }
  .hint { display: flex; align-items: center; gap: 0.35rem; font-size: 0.75rem; color: var(--muted); }
  .send {
    display: grid;
    place-items: center;
    width: 2rem;
    height: 2rem;
    border-radius: 50%;
    background: linear-gradient(135deg, #b672ff, #7c3ae0);
    color: #fff;
  }

  .tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.75rem; }
  .tile {
    display: grid;
    gap: 0.4rem;
    align-content: start;
    text-align: left;
    padding: 0.85rem 0.9rem 0.95rem;
    border-radius: 14px;
    background: rgba(10, 8, 12, 0.6);
    border: 1px solid var(--line);
  }
  .tile:hover:not(:disabled) { border-color: var(--line-strong); background: rgba(20, 16, 24, 0.8); }
  .tile-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem; }
  .tile-icon {
    display: grid;
    place-items: center;
    width: 1.8rem;
    height: 1.8rem;
    border-radius: 8px;
    background: var(--surface-2);
    color: var(--accent-soft);
  }
  .tile-title { font-weight: 600; font-size: 0.875rem; }
  .tile-text { font-weight: 400; font-size: 0.8125rem; color: var(--muted); line-height: 1.45; }

  .error { color: var(--fault); }

  @media (max-width: 56rem) {
    .app { grid-template-columns: 1fr; height: auto; min-height: 100dvh; }
    .sidebar { overflow: visible; }
    .note { margin-top: 0; }
    .panel { min-height: 90dvh; }
    .tiles { grid-template-columns: 1fr; }
    .approval { flex-direction: column; align-items: flex-start; }
    .dock, .thread { padding-inline: 1rem; }
  }
</style>
