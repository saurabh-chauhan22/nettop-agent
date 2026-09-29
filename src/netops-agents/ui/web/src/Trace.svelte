<script>
  // A modem's SNR over 24 hours with the anomaly window shaded.
  // Fixed 15 to 45 dB scale, so a dip on one modem is comparable to every other row.
  let { snr, ts, start, end } = $props();

  const W = 320, H = 48, LO = 15, HI = 45;
  const x = (i) => (i / (snr.length - 1)) * W;
  const y = (v) => H - ((Math.min(Math.max(v, LO), HI) - LO) / (HI - LO)) * H;

  let points = $derived(snr.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' '));
  let first = $derived(ts.findIndex((t) => t >= start));
  let last = $derived(ts.findLastIndex((t) => t <= end));
  let min = $derived(Math.min(...snr).toFixed(1));
</script>

<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img"
     aria-label="SNR over 24 hours, lowest {min} dB. Shaded band is the anomaly window.">
  {#if first >= 0 && last >= first}
    <rect class="window" x={x(first)} y="0" width={Math.max(x(last) - x(first), 2)} height={H} />
  {/if}
  <polyline class="trace" {points} />
</svg>

<style>
  svg {
    display: block;
    width: 100%;
    height: var(--trace-height, 3rem);
    background: var(--plate);
    border-radius: 2px;
  }
  .window { fill: var(--fault-wash); }
  .trace {
    fill: none;
    stroke: var(--trace);
    stroke-width: 1.5;
    vector-effect: non-scaling-stroke;
    stroke-linejoin: round;
  }
</style>
