<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import WaveSurfer from 'wavesurfer.js';
  import { fetchSceneMetrics, retryScene, API_BASE } from '../api';

  interface Props {
    projectId: string;
    sceneId: string;
    wavUrl: string;
    instruct: string;
    voice: string;
    onRetry?: () => void;
  }

  let { projectId, sceneId, wavUrl, instruct, voice, onRetry }: Props = $props();

  let container = $state<HTMLElement | null>(null);
  let wavesurfer = $state<WaveSurfer | null>(null);
  let metrics = $state<any>(null);
  let loadingMetrics = $state(true);
  let retrying = $state(false);
  let isPlaying = $state(false);
  let editableInstruct = $state(instruct);

  onMount(async () => {
    // Initialize WaveSurfer
    if (container) {
      wavesurfer = WaveSurfer.create({
        container,
        waveColor: '#475569',
        progressColor: '#38bdf8',
        cursorColor: '#0ea5e9',
        barWidth: 2,
        barRadius: 3,
        responsive: true,
        height: 60,
        normalize: true,
      });

      // Local assets need absolute URL from API_BASE if not starting with /
      const fullUrl = wavUrl.startsWith('http') ? wavUrl : `${API_BASE}${wavUrl}`;
      wavesurfer.load(fullUrl);

      wavesurfer.on('play', () => isPlaying = true);
      wavesurfer.on('pause', () => isPlaying = false);
      wavesurfer.on('finish', () => isPlaying = false);
    }

    // Fetch Metrics
    try {
      metrics = await fetchSceneMetrics(projectId, sceneId);
    } catch (e) {
      console.error('Failed to load metrics:', e);
    } finally {
      loadingMetrics = false;
    }
  });

  onDestroy(() => {
    if (wavesurfer) wavesurfer.destroy();
  });

  const handleRetry = async () => {
    if (!confirm('Rilanciare la generazione per questa scena?')) return;
    retrying = true;
    try {
      await retryScene(projectId, sceneId, editableInstruct);
      alert('Richiesta di rigenerazione inviata!');
      if (onRetry) onRetry();
    } catch (e) {
      alert(`Errore: ${(e as Error).message}`);
    } finally {
      retrying = false;
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 0.8) return 'text-emerald-400 border-emerald-500/20 bg-emerald-500/10';
    if (score >= 0.5) return 'text-amber-400 border-amber-500/20 bg-amber-500/10';
    return 'text-rose-400 border-rose-500/20 bg-rose-500/10';
  };
</script>

<div class="space-y-4">
  <!-- Waveform Inspector -->
  <div class="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3">
    <div class="flex items-center justify-between mb-2">
      <p class="text-[9px] font-black text-slate-500 uppercase tracking-widest">Acoustic Inspector</p>
      <div class="flex items-center gap-2">
        <div class="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-[10px] font-mono text-sky-400">
          Voice: {voice}
        </div>
        {#if metrics}
          <div class="px-2 py-0.5 rounded-full border text-[10px] font-bold {getScoreColor(metrics.quality_score)}">
            QC Score: {Math.round(metrics.quality_score * 100)}%
          </div>
        {/if}
      </div>
    </div>
    
    <div bind:this={container} class="w-full"></div>
    
    <div class="flex items-center gap-3">
      <button 
        onclick={() => wavesurfer?.togglePlay()}
        class="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-bold transition-all flex items-center gap-2"
      >
        {#if isPlaying}
          <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
          Pause
        {:else}
          <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Preview
        {/if}
      </button>

      {#if loadingMetrics}
        <div class="text-[10px] text-slate-600 animate-pulse">Analyzing audio metrics...</div>
      {:else if metrics}
        <div class="flex gap-4 text-[10px] font-mono text-slate-400">
          <span>Pitch: <b class="text-slate-200">{metrics.pitch_avg_hz}Hz</b></span>
          <span>RMS: <b class="text-slate-200">{metrics.rms_avg}</b></span>
          <span>Brightness: <b class="text-slate-200">{metrics.brightness_avg_hz}Hz</b></span>
          <span>Silence: <b class="text-slate-200">{Math.round(metrics.silence_ratio*100)}%</b></span>
        </div>
      {/if}
    </div>
  </div>

  <!-- Director's Console -->
  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <div class="md:col-span-2 space-y-2">
      <p class="text-[9px] font-black text-slate-500 uppercase tracking-widest">Director's Instruct Override</p>
      <textarea 
        bind:value={editableInstruct}
        class="w-full h-20 p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 focus:border-sky-500 outline-none transition-all resize-none"
        placeholder="Change instruction for this specific scene..."
      ></textarea>
    </div>
    
    <div class="flex flex-col justify-end gap-2">
      <button 
        onclick={handleRetry}
        disabled={retrying}
        class="w-full py-3 rounded-xl bg-sky-500 hover:bg-sky-400 text-white text-[10px] font-black uppercase tracking-widest transition-all active:scale-95 disabled:opacity-50 shadow-lg shadow-sky-500/20"
      >
        {retrying ? 'Re-queuing...' : '🚀 Re-generate Scene'}
      </button>
      <p class="text-[9px] text-slate-600 text-center italic">This will overwrite the current WAV.</p>
    </div>
  </div>
</div>
