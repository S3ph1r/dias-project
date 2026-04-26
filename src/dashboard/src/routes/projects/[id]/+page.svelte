<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { slide } from 'svelte/transition';
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import {
    fetchProjectDetails, pushSceneToStageD, fetchVoices, resumePipeline,
    checkResume, resetStage, fetchChapters, fetchFingerprint, fetchPreproduction,
    analyzeProject, fetchWorkerStatus, triggerAudiobookMaster, fetchProjectLiveStatus,
    fetchAudiobookChapters, clearPipelinePause,
    API_BASE,
    type Project, type ProjectStage, type ChapterSummary, type Fingerprint,
    type PreproductionData, type AudiobookChapter
  } from '../../../lib/api';
  import { playScene } from '$lib/player.svelte';
  import AudioInspector from '$lib/components/AudioInspector.svelte';
  import CastingTable from '$lib/components/CastingTable.svelte';
  import VoiceCarousel from '$lib/components/VoiceCarousel.svelte';

  let project = $state<Project | null>(null);
  let chapters = $state<ChapterSummary[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let processingScene = $state<string | null>(null);
  let resetting = $state<string | null>(null);
  let resuming = $state(false);
  let autoRefreshEnabled = $state(true);
  let refreshInterval: any;
  let activeTab = $state<'chapters' | 'stages' | 'preproduction' | 'audiobook'>('chapters');
  let expandedChunks = $state(new Set<string>());
  let expandedScenes = $state(new Set<string>());
  
  let fingerprint = $state<Fingerprint | null>(null);
  let preproduction = $state<PreproductionData | null>(null);
  let loadingPreprod = $state(false);
  let analyzing = $state(false);
  let voices = $state<Record<string, any>>({});
  let selectedVoice = $state<string | null>(null);
  let workerStatus = $state<Record<string, 'running' | 'stopped'>>({});
  let pausedReason = $state<string | null>(null);
  let unpausing = $state(false);

  // Audiobook player state
  let audiobookChapters = $state<AudiobookChapter[]>([]);
  let audioEl = $state<HTMLAudioElement | null>(null);
  let playerCurrentTime = $state(0);
  let playerDuration = $state(0);
  let playerPlaying = $state(false);
  let playerSeeking = $state(false);

  const currentChapterIndex: number = $derived.by(() => {
    if (!audiobookChapters.length || playerDuration === 0) return -1;
    const ms = playerCurrentTime * 1000;
    for (let i = audiobookChapters.length - 1; i >= 0; i--) {
      if (ms >= audiobookChapters[i].start_ms) return i;
    }
    return 0;
  });

  function formatTime(secs: number): string {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = Math.floor(secs % 60);
    return h > 0
      ? `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
      : `${m}:${String(s).padStart(2,'0')}`;
  }

  function seekToChapter(chapter: AudiobookChapter) {
    if (audioEl) {
      audioEl.currentTime = chapter.start_ms / 1000;
      audioEl.play();
    }
  }

  // Derived sorted list of voice IDs for backwards compatibility and UI loops
  const voiceIds = $derived(Object.keys(voices).sort());
  const isPipelineRunning = $derived(workerStatus.orchestrator === 'running');
  const isPipelinePaused = $derived(!!pausedReason);
  const activeWorkerName = $derived(
    isPipelinePaused ? 'Paused' :
    workerStatus.orchestrator !== 'running' ? (project?.status === 'completed' ? 'Completed' : 'Pipeline Idle') :
    (project?.active_stage === 'stage_a' ? 'Stage A' :
     project?.active_stage === 'stage_b' ? 'Stage B' :
     project?.active_stage === 'stage_c' ? 'Stage C' :
     project?.active_stage === 'stage_d' ? 'Stage D' :
     'Orchestrator')
  );

  const loadData = async (silent = false) => {
    if (!silent) loading = true;
    try {
      const [details, voiceData, chapterData, statusData] = await Promise.all([
        fetchProjectDetails(page.params.id),
        fetchVoices(),
        fetchChapters(page.params.id),
        fetchWorkerStatus()
      ]);

      // Update state only if changed to avoid unnecessary re-renders
      if (JSON.stringify(project) !== JSON.stringify(details)) project = details;
      if (JSON.stringify(voices) !== JSON.stringify(voiceData.voices)) voices = voiceData.voices;
      if (JSON.stringify(chapters) !== JSON.stringify(chapterData)) chapters = chapterData;
      if (JSON.stringify(workerStatus) !== JSON.stringify(statusData.workers)) workerStatus = statusData.workers;
      
      if (voiceIds.length > 0 && !selectedVoice) {
        selectedVoice = voiceIds[0];
      }

      // Proactive load: if project is already analyzed, fetch fingerprint immediately
      const isAnalyzed = details?.status === 'analisi_completed' || details?.status === 'ready';
      if (isAnalyzed && !fingerprint) {
        await loadPreprodData();
      }

      // Pre-load pre-production if tab is active and not yet loaded
      if (activeTab === 'preproduction' && !preproduction) {
        await loadPreprodData();
      }
    } catch (e) {
      error = (e as Error).message;
    } finally {
      if (!silent) loading = false;
    }
  };

  const loadPreprodData = async () => {
    loadingPreprod = true;
    try {
      const fp = await fetchFingerprint(page.params.id);
      const pp = await fetchPreproduction(page.params.id);
      fingerprint = fp;
      preproduction = pp;
      if (pp.global_voice && voices[pp.global_voice]) {
        selectedVoice = pp.global_voice;
      }
    } catch (e) {
      console.error('Failed to load pre-production data:', e);
    } finally {
      loadingPreprod = false;
    }
  };

  const handleStartAnalysis = async () => {
    if (!project) return;
    analyzing = true;
    try {
      await analyzeProject(project.id);
      alert('Analisi Intelligence (Stage 0) avviata!');
      await loadData(true);
    } catch (e) {
      alert(`Errore: ${(e as Error).message}`);
    } finally {
      analyzing = false;
    }
  };

  // Lightweight poll: updates only status/stage/workers — no heavy file lists
  const pollLiveStatus = async () => {
    if (!autoRefreshEnabled || loading || resuming || resetting) return;
    try {
      const live = await fetchProjectLiveStatus(page.params.id);
      if (project) {
        project = { ...project, status: live.status, active_stage: live.active_stage };
      }
      const nextWorkers = { ...workerStatus, orchestrator: live.orchestrator_running ? 'running' as const : 'stopped' as const };
      if (JSON.stringify(workerStatus) !== JSON.stringify(nextWorkers)) {
        workerStatus = nextWorkers;
      }
      pausedReason = live.paused_reason ?? null;
    } catch (e) {
      // Non-critical — swallow poll errors silently
    }
  };

  onMount(() => {
    loadData();

    const startPolling = () => {
      clearInterval(refreshInterval);
      refreshInterval = setInterval(pollLiveStatus, 60000);
    };

    const handleVisibilityChange = () => {
      if (document.hidden) {
        clearInterval(refreshInterval);
      } else {
        // Tab back in focus: full reload then resume polling
        loadData(true);
        startPolling();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    startPolling();

    return () => {
      clearInterval(refreshInterval);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  });

  const toggleChunk = (id: string) => {
    const next = new Set(expandedChunks);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    expandedChunks = next;
  };

  const toggleScene = (id: string) => {
    const next = new Set(expandedScenes);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    expandedScenes = next;
  };

  const statusConfig = {
    pending:     { label: 'Pending',     cls: 'text-slate-500 bg-slate-500/10 border-slate-500/20',   dot: 'bg-slate-500' },
    scripted:    { label: 'Scripted',    cls: 'text-violet-400 bg-violet-400/10 border-violet-400/20', dot: 'bg-violet-400' },
    in_progress: { label: 'Recording',  cls: 'text-sky-400 bg-sky-400/10 border-sky-400/20',          dot: 'bg-sky-400 animate-pulse' },
    voice_done:  { label: 'Voice Done', cls: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20', dot: 'bg-emerald-400' },
    done:        { label: 'Done',       cls: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20', dot: 'bg-emerald-400' },
    in_progress_stage: { label: 'In Progress', cls: 'text-sky-400 bg-sky-400/10 border-sky-400/20', dot: 'bg-sky-400 animate-pulse' }
  } as const;

  const getChunkStatusCfg = (s: string) =>
    statusConfig[s as keyof typeof statusConfig] ?? statusConfig.pending;

  const handleResumePipeline = async () => {
    if (!project) return;
    resuming = true;
    try {
      const check = await checkResume(project.id);
      const existingVoices = Object.keys(check.voices).filter(v => v !== 'none' && v !== selectedVoice);
      if (existingVoices.length > 0) {
        const counts = existingVoices.map(v => `${check.voices[v]} scene con voce '${v}'`).join(', ');
        const msg = `ATTENZIONE: ${counts}.\n\nVoce selezionata: '${selectedVoice || 'default'}'. Continuare?`;
        if (!confirm(msg)) return;
      }
      const result = await resumePipeline(project.id, selectedVoice || undefined);
      alert(`Pipeline ripresa! Inviati ${result.pushed_count} task ad ARIA.`);
      await loadData(true);
      await pollLiveStatus();
    } catch (e) {
      alert(`Errore: ${(e as Error).message}`);
    } finally {
      resuming = false;
    }
  };

  const handleClearPause = async () => {
    if (!project) return;
    unpausing = true;
    try {
      const result = await clearPipelinePause(project.id);
      pausedReason = null;
      alert(result.message);
    } catch (e) {
      alert(`Errore: ${(e as Error).message}`);
    } finally {
      unpausing = false;
    }
  };

  const handleTriggerMaster = async () => {
    if (!project) return;
    try {
      await triggerAudiobookMaster(project.id);
      alert('Stage F avviato! Il file .m4b sarà disponibile a breve.');
      await loadData(true);
    } catch (e) {
      alert(`Errore: ${(e as Error).message}`);
    }
  };

  $effect(() => {
    if (activeTab === 'audiobook' && project?.audiobook && audiobookChapters.length === 0) {
      fetchAudiobookChapters(page.params.id).then(chs => { audiobookChapters = chs; });
    }
  });

  const handleResetStage = async (stageId: string) => {
    if (!project) return;
    if (!confirm(`SEI SICURO? Cancellerà tutti i file di ${stageId} per questo progetto.`)) return;
    resetting = stageId;
    try {
      await resetStage(project.id, stageId);
      alert(`Stage ${stageId} resettato.`);
      await loadData(true);
    } catch (e) {
      alert(`Error: ${(e as Error).message}`);
    } finally {
      resetting = null;
    }
  };

  const handlePushScene = async (projectId: string, sceneFile: string) => {
    processingScene = sceneFile;
    try {
      await pushSceneToStageD(projectId, sceneFile, selectedVoice || undefined);
      alert(`Scene ${sceneFile} pushed successfully!`);
      await loadData(true);
    } catch (e) {
      alert(`Error: ${(e as Error).message}`);
    } finally {
      processingScene = null;
    }
  };

  // Summary counts from chapter data
  const chapterStats = $derived({
    total: chapters.length,
    voice_done: chapters.filter(c => c.status === 'voice_done').length,
    in_progress: chapters.filter(c => c.status === 'in_progress').length,
    total_scenes: chapters.reduce((a, c) => a + (c.scene_count || 0), 0),
    total_wavs: chapters.reduce((a, c) => a + (c.wav_count || 0), 0),
  });
</script>

<div class="px-8 py-10 max-w-7xl mx-auto space-y-8">
  <!-- Header -->
  <header class="space-y-4">
    <div class="flex items-center gap-4">
      <a href={resolve('/')} class="p-2 rounded-lg bg-slate-900 border border-slate-800 hover:bg-slate-800 transition-colors">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-5 h-5"><path d="m15 18-6-6 6-6"/></svg>
      </a>
      <div class="h-px flex-1 bg-slate-800"></div>
      {#if autoRefreshEnabled}
        <div class="flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20">
          <div class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></div>
          <span class="text-[10px] font-black text-emerald-500 uppercase tracking-widest">Live</span>
        </div>
      {/if}
      <button
        onclick={() => autoRefreshEnabled = !autoRefreshEnabled}
        class="text-[10px] font-bold uppercase tracking-widest {autoRefreshEnabled ? 'text-slate-400' : 'text-slate-600'} hover:text-white transition-colors"
      >{autoRefreshEnabled ? 'Pause Refresh' : 'Enable Refresh'}</button>
    </div>

    <div class="flex justify-between items-end flex-wrap gap-4">
      <div class="space-y-1">
        <h2 class="text-5xl font-black tracking-tighter uppercase italic">{project?.name || 'Loading...'}</h2>
        <p class="text-slate-400 font-mono text-sm tracking-widest">{project?.id || '...'}</p>
      </div>

      <!-- Voice selector + Resume -->
        <!-- Voice selector (Global Override moved later in Phase 2) -->
      </div>
  </header>

  {#if loading}
    <div class="space-y-4 animate-pulse">
      <div class="h-24 bg-slate-900/50 rounded-2xl border border-slate-800"></div>
      <div class="h-24 bg-slate-900/50 rounded-2xl border border-slate-800"></div>
      <div class="h-24 bg-slate-900/50 rounded-2xl border border-slate-800"></div>
    </div>
  {:else if error}
    <div class="p-8 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 font-medium">{error}</div>
  {:else}

    <!-- Summary stats bar -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div class="bg-slate-900/40 backdrop-blur-xl border border-slate-800 p-5 rounded-2xl space-y-1">
        <p class="text-slate-500 font-bold uppercase text-[10px] tracking-widest">Chunks</p>
        <p class="text-3xl font-black text-white">{chapterStats.total}</p>
      </div>
      <div class="bg-slate-900/40 backdrop-blur-xl border border-slate-800 p-5 rounded-2xl space-y-1">
        <p class="text-slate-500 font-bold uppercase text-[10px] tracking-widest">Total Scenes</p>
        <p class="text-3xl font-black text-white">{chapterStats.total_scenes}</p>
      </div>
      <div class="bg-slate-900/40 backdrop-blur-xl border border-slate-800 p-5 rounded-2xl space-y-1">
        <p class="text-slate-500 font-bold uppercase text-[10px] tracking-widest">WAV Generated</p>
        <p class="text-3xl font-black text-emerald-400">{chapterStats.total_wavs}</p>
      </div>
      <div class="bg-slate-900/40 backdrop-blur-xl border border-slate-800 p-5 rounded-2xl space-y-1">
        <p class="text-slate-500 font-bold uppercase text-[10px] tracking-widest">Overall</p>
        <p class="text-3xl font-black text-sky-400">{project?.overall_progress || 0}%</p>
      </div>
    </div>

    <!-- Tabs & Actions -->
    <div class="flex items-center justify-between gap-4">
      <div class="flex gap-1 p-1 bg-slate-900/60 border border-slate-800 rounded-xl w-fit">
        <button
          onclick={() => activeTab = 'chapters'}
          class="px-5 py-2 rounded-lg text-sm font-bold transition-all {activeTab === 'chapters' ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/20' : 'text-slate-400 hover:text-white'}"
        >📚 Chapter Timeline</button>
        <button
          onclick={() => { activeTab = 'preproduction'; loadPreprodData(); }}
          class="px-5 py-2 rounded-lg text-sm font-bold transition-all {activeTab === 'preproduction' ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/20' : 'text-slate-400 hover:text-white'}"
        >🎭 Pre-production</button>
        <button
          onclick={() => activeTab = 'stages'}
          class="px-5 py-2 rounded-lg text-sm font-bold transition-all {activeTab === 'stages' ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/20' : 'text-slate-400 hover:text-white'}"
        >⚙️ Stage Details</button>
        <button
          onclick={() => activeTab = 'audiobook'}
          class="px-5 py-2 rounded-lg text-sm font-bold transition-all {activeTab === 'audiobook' ? 'bg-emerald-500 text-white shadow-lg shadow-emerald-500/20' : 'text-slate-400 hover:text-white'}"
        >🎧 Audiobook</button>
      </div>

      {#if project && (project.overall_progress ?? 0) < 100}
        <div class="flex items-center gap-3">
          <!-- Status pill: amber when paused, green when running, grey when idle -->
          <div class="flex items-center gap-2 px-3 py-1.5 rounded-full {
            isPipelinePaused ? 'bg-amber-500/10 border-amber-500/30 text-amber-400' :
            activeWorkerName === 'Pipeline Idle' ? 'bg-slate-800 border-slate-700 text-slate-500' :
            activeWorkerName === 'Completed' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' :
            'bg-emerald-500/10 border-emerald-500/20 text-emerald-400 animate-pulse'
          } border text-[10px] font-black uppercase tracking-widest shadow-lg shadow-emerald-500/5">
            <div class="{isPipelinePaused ? 'w-1.5 h-1.5 rounded-full bg-amber-500' : activeWorkerName === 'Pipeline Idle' ? 'w-1.5 h-1.5 rounded-full bg-slate-600' : 'w-1.5 h-1.5 rounded-full bg-emerald-500'}"></div>
            {activeWorkerName}
          </div>

          {#if isPipelinePaused}
            <!-- Pause banner + unlock button -->
            <div class="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-[10px] font-semibold max-w-xs truncate" title={pausedReason ?? ''}>
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
              {pausedReason}
            </div>
            <button
              onclick={handleClearPause}
              disabled={unpausing}
              class="px-6 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-900 text-xs font-black uppercase tracking-widest transition-all active:scale-95 disabled:opacity-50 flex items-center gap-2 shadow-lg shadow-amber-500/20"
            >
              {#if unpausing}
                <div class="w-3.5 h-3.5 border-2 border-slate-900/30 border-t-slate-900 rounded-full animate-spin"></div>
                Sbloccando...
              {:else}
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg>
                Sblocca Pausa
              {/if}
            </button>
          {:else}
            <!-- Normal start/resume button -->
            <button
              onclick={handleResumePipeline}
              disabled={resuming || isPipelineRunning}
              class="px-6 py-2.5 rounded-xl {isPipelineRunning ? 'bg-slate-800 text-slate-500 cursor-not-allowed' : 'bg-sky-500 hover:bg-sky-400 text-white shadow-lg shadow-sky-500/20'} text-xs font-black uppercase tracking-widest transition-all active:scale-95 disabled:opacity-50 flex items-center gap-2"
            >
              {#if resuming}
                <div class="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                Resuming...
              {:else}
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m5 3 14 9-14 9V3z"/></svg>
                {(project?.overall_progress ?? 0) === 0 ? 'Start Production' : 'Resume Pipeline'}
              {/if}
            </button>
          {/if}
        </div>
    {:else if project}
        <div class="px-4 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-black uppercase tracking-widest flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          Completed
        </div>
      {/if}
    </div>

    <!-- Voice Control Carousel (Phase 2) -->
    {#if voiceIds.length > 0}
      <div class="bg-slate-900/40 backdrop-blur-xl border border-slate-800 rounded-3xl p-6 shadow-2xl">
        <VoiceCarousel 
          {voices} 
          {selectedVoice} 
          onSelect={(id) => selectedVoice = id} 
        />
      </div>
    {/if}

    <!-- CHAPTER TIMELINE TAB -->
    {#if activeTab === 'chapters'}
      <div class="space-y-3">
        {#if chapters.length === 0}
          <div class="py-16 text-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/20 space-y-6">
            <div class="space-y-2">
              <p class="text-slate-500 italic">No chapter data available yet. Stage C must complete first.</p>
              {#if !fingerprint}
                <p class="text-slate-400 text-sm">Il progetto è nuovo. Avvia l'intelligenza per estrarre la struttura.</p>
              {/if}
            </div>
            
            {#if !fingerprint}
              <button 
                onclick={handleStartAnalysis}
                disabled={analyzing}
                class="px-8 py-3 rounded-2xl bg-sky-500 hover:bg-sky-400 text-white font-black uppercase tracking-widest transition-all active:scale-95 disabled:opacity-50 shadow-lg shadow-sky-500/20"
              >
                {analyzing ? 'Analysis In Progress...' : '🚀 Start Stage 0 Analysis'}
              </button>
            {/if}
          </div>
        {:else}
          {#each chapters as chunk}
            {@const cfg = getChunkStatusCfg(chunk.status)}
            <div class="bg-slate-900/40 backdrop-blur-xl border border-slate-800 rounded-2xl overflow-hidden transition-all hover:border-slate-700">
              <!-- Chunk header row -->
              <button
                onclick={() => toggleChunk(chunk.chunk_id)}
                class="w-full flex items-center gap-5 p-5 text-left"
              >
                <!-- Status dot -->
                <div class="w-3 h-3 rounded-full {cfg.dot} shadow-[0_0_8px_rgba(0,0,0,0.3)] flex-shrink-0"></div>

                <!-- Title & ID -->
                <div class="flex-1 min-w-0">
                  <p class="font-bold text-white truncate">{chunk.title}</p>
                  <p class="text-[10px] font-mono text-slate-500">{chunk.chunk_id} · {chunk.scene_count} scene</p>
                </div>

                <!-- Progress bar -->
                <div class="w-48 flex-shrink-0 space-y-1 hidden md:block">
                  <div class="h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      class="h-full rounded-full transition-all duration-700 {chunk.status === 'voice_done' ? 'bg-emerald-500' : chunk.status === 'in_progress' ? 'bg-sky-500' : chunk.status === 'scripted' ? 'bg-violet-500' : 'bg-slate-700'}"
                      style="width: {chunk.progress_pct}%"
                    ></div>
                  </div>
                  <p class="text-[10px] text-slate-500 text-right font-mono">{chunk.wav_count}/{chunk.scene_count} WAV</p>
                </div>

                <!-- Badge -->
                <span class="px-3 py-1 rounded-full border text-[10px] font-black uppercase tracking-wider flex-shrink-0 {cfg.cls}">
                  {cfg.label}
                </span>

                <!-- Expand icon -->
                <svg
                  xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
                  fill="none" stroke="currentColor" stroke-width="2"
                  class="text-slate-600 transition-transform flex-shrink-0 {expandedChunks.has(chunk.chunk_id) ? 'rotate-180' : ''}"
                >
                  <path d="m6 9 6 6 6-6"/>
                </svg>
              </button>

              <!-- Expanded scene list -->
              {#if expandedChunks.has(chunk.chunk_id)}
                <div class="border-t border-slate-800 p-4 space-y-2">
                  <p class="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">Scenes in this chunk</p>
                  <div class="grid gap-2 max-h-[280px] overflow-y-auto pr-1 custom-scrollbar">
                    {#each chunk.scenes as scene}
                      <div class="flex flex-col rounded-xl bg-slate-950/50 border border-slate-800 overflow-hidden">
                        <div class="flex items-center justify-between p-3 gap-3">
                          <button 
                            onclick={() => toggleScene(scene.id)}
                            class="flex items-center gap-2 flex-1 min-w-0 text-left hover:text-sky-400 transition-colors"
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-slate-500 {expandedScenes.has(scene.id) ? 'rotate-90' : ''} transition-transform"><path d="m9 18 6-6-6-6"/></svg>
                            <span class="text-xs font-mono truncate">{scene.id}</span>
                          </button>
                          
                          <div class="flex items-center gap-2">
                            {#if scene.wav_url}
                              <button 
                                onclick={() => playScene(scene.id, scene.wav_url!)}
                                class="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500 hover:text-white transition-all active:scale-95"
                                title="Play Scene"
                              >
                                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" class="translate-x-0.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                              </button>
                            {/if}

                            <span class="w-2 h-2 rounded-full flex-shrink-0 {scene.wav_url ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]' : 'bg-slate-600'}"></span>
                          </div>
                        </div>

                        {#if expandedScenes.has(scene.id)}
                          <div class="px-3 pb-4 pt-1 border-t border-slate-800/50 bg-slate-900/30 space-y-3 animate-in fade-in slide-in-from-top-1 duration-200" transition:slide>
                            {#if scene.wav_url}
                              <AudioInspector
                                projectId={project?.id || ''}
                                sceneId={scene.id}
                                wavUrl={scene.wav_url}
                                voice={scene.voice}
                                instruct={scene.instruct}
                                onRetry={() => loadData(true)}
                              />
                            {:else}
                              <div class="grid grid-cols-2 gap-4">
                                <div>
                                  <p class="text-[9px] font-black text-slate-500 uppercase tracking-widest mb-1">Voice (Planned)</p>
                                  <div class="px-2 py-1 rounded bg-slate-950 border border-slate-800 text-[11px] text-slate-500 inline-block font-mono">
                                    {scene.voice}
                                  </div>
                                </div>
                                <div class="text-right">
                                  <p class="text-[9px] font-black text-slate-500 uppercase tracking-widest mb-1">Status</p>
                                  <div class="px-2 py-1 rounded bg-slate-950 border border-slate-800 text-[11px] text-slate-500 inline-block font-mono">
                                    Waiting for production...
                                  </div>
                                </div>
                              </div>
                              <div>
                                <p class="text-[9px] font-black text-slate-500 uppercase tracking-widest mb-1">Original Text</p>
                                <div class="p-2 rounded bg-slate-950 border border-slate-800 text-[11px] text-slate-300 leading-relaxed font-serif">
                                  {scene.text}
                                </div>
                              </div>
                            {/if}
                          </div>
                        {/if}
                      </div>
                    {/each}
                  </div>
                </div>
              {/if}
            </div>
          {/each}
        {/if}
      </div>
    {/if}

    <!-- PRE-PRODUCTION / CASTING TAB -->
    {#if activeTab === 'preproduction'}
      <div class="space-y-6">
        {#if !fingerprint}
          <div class="py-20 text-center rounded-3xl border border-dashed border-slate-800 bg-slate-900/40 backdrop-blur-xl space-y-4">
            <div class="flex justify-center">
              <div class="p-4 rounded-full bg-sky-500/10 border border-sky-500/20 text-sky-400">
                <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/><path d="M22 10 12 11.2V3"/><path d="M12 10V2"/><path d="M12 2a10 10 0 0 0-10 10c0 5.523 4.477 10 10 10s10-4.477 10-10a10 10 0 0 0-8.57-9.88"/></svg>
              </div>
            </div>
            <div class="space-y-1">
              <h3 class="text-xl font-black text-white uppercase italic">Intelligence Required</h3>
              <p class="text-slate-500 max-w-sm mx-auto text-sm leading-relaxed">
                Questo progetto non è ancora stato analizzato. Avvia l'analisi Stage 0 per scoprire personaggi e struttura.
              </p>
            </div>
            <button 
              onclick={handleStartAnalysis}
              disabled={analyzing}
              class="px-8 py-3 rounded-2xl bg-sky-500 hover:bg-sky-400 text-white font-black uppercase tracking-widest transition-all active:scale-95 disabled:opacity-50 shadow-lg shadow-sky-500/20"
            >
              {analyzing ? 'Analysis In Progress...' : '🚀 Start Stage 0 Analysis'}
            </button>
          </div>
        {:else if loadingPreprod}
          <div class="py-20 text-center animate-pulse">
            <p class="text-slate-500 font-mono text-sm tracking-widest">Loading Artist Dossier...</p>
          </div>
        {:else if preproduction}
          <CastingTable 
            projectId={project?.id || ''}
            {fingerprint}
            {preproduction}
            {voices}
            globalVoice={selectedVoice}
            onSaved={() => loadData(true)}
          />
        {/if}
      </div>
    {/if}

    <!-- STAGE DETAILS TAB -->
    {#if activeTab === 'stages' && project}
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {#each (project.stages ?? []) as stage}
          <div class="bg-slate-900/40 backdrop-blur-xl border border-slate-800 rounded-3xl p-7 space-y-5 flex flex-col {stage.is_placeholder ? 'opacity-40 grayscale pointer-events-none' : ''}">
            <div class="flex justify-between items-start">
              <div class="space-y-1">
                <p class="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">{stage.id}</p>
                <div class="flex items-center gap-2">
                  <h3 class="text-xl font-black text-white">{stage.name}</h3>
                  {#if workerStatus[stage.id] === 'running'}
                    <div class="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)] animate-pulse" title="Worker Active"></div>
                  {/if}
                </div>
              </div>
              <div class="flex items-center gap-3">
                <button
                  onclick={() => handleResetStage(stage.id)}
                  disabled={resetting === stage.id}
                  title="Reset this stage"
                  class="p-2 rounded-xl bg-rose-500/10 text-rose-500 border border-rose-500/20 hover:bg-rose-500/20 transition-all active:scale-95 disabled:opacity-50"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" class={resetting === stage.id ? 'animate-spin' : ''}><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>
                </button>
                <span class="px-3 py-1 rounded-full border text-[10px] font-black uppercase tracking-wider {stage.status === 'done' ? 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20' : stage.status === 'in_progress' ? 'text-sky-400 bg-sky-400/10 border-sky-400/20' : 'text-slate-500 bg-slate-500/10 border-slate-500/20'}">
                  {stage.status.replace('_', ' ')}
                </span>
              </div>
            </div>

            <div class="flex-1 space-y-3 overflow-hidden">
              <p class="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Assets ({stage.files.filter(f => stage.id !== 'stage_d' || f.endsWith('.wav')).length})</p>
              <div class="max-h-[240px] overflow-y-auto space-y-2 pr-1 custom-scrollbar">
                {#each stage.files.filter(f => stage.id !== 'stage_d' || f.endsWith('.wav')) as file}
                  <div class="group flex items-center justify-between p-3 rounded-xl bg-slate-950/50 border border-slate-800 hover:border-slate-700 transition-all">
                    <span class="text-xs font-mono text-slate-300 truncate flex-1">{file}</span>
                    
                    <div class="flex items-center gap-2">
                      {#if stage.id === 'stage_d' && file.endsWith('.wav')}
                        <button 
                          onclick={() => {
                            const match = file.match(/scene-(\d{3})/);
                            const sceneId = match ? match[1] : file;
                            playScene(sceneId, `/static/projects/${project?.id}/stages/stage_d/output/${file}`);
                          }}
                          class="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500 hover:text-white transition-all active:scale-95"
                          title="Play Asset"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" class="translate-x-0.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                        </button>
                      {/if}

                      {#if stage.id === 'stage_c'}
                        <button
                          onclick={() => handlePushScene(project!.id, file)}
                          disabled={processingScene === file}
                          class="ml-3 px-3 py-1 rounded-lg bg-sky-500 hover:bg-sky-400 text-white text-[10px] font-black uppercase tracking-widest transition-all active:scale-95 disabled:opacity-50"
                        >{processingScene === file ? '...' : 'Push'}</button>
                      {/if}
                    </div>
                  </div>
                {:else}
                  <p class="text-slate-600 text-xs italic">No assets yet.</p>
                {/each}
              </div>
            </div>
          </div>
        {/each}
      </div>
    {/if}
    
    <!-- AUDIOBOOK TAB -->
    {#if activeTab === 'audiobook' && project}
      <div class="space-y-6">
        {#if project.audiobook}
          {@const audioSrc = project.audiobook.url.startsWith('http') || project.audiobook.url.startsWith('/') ? project.audiobook.url : `${API_BASE}/${project.audiobook.url}`}
          <div class="bg-slate-900/40 backdrop-blur-xl border border-slate-800 rounded-3xl p-8 space-y-8 shadow-2xl">

            <!-- Header -->
            <div class="flex items-center justify-between">
              <div class="space-y-1">
                <h3 class="text-2xl font-black text-white italic uppercase tracking-tighter">Audiobook Master</h3>
                <p class="text-slate-500 font-mono text-xs uppercase tracking-widest">{project.audiobook.filename} · {(project.audiobook.size / (1024*1024)).toFixed(1)} MB · AAC 128kbps</p>
              </div>
              <div class="px-4 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-black uppercase tracking-widest flex items-center gap-2">
                <div class="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
                Ready
              </div>
            </div>

            <!-- Hidden audio element -->
            <audio
              bind:this={audioEl}
              src={audioSrc}
              ontimeupdate={() => { if (!playerSeeking && audioEl) playerCurrentTime = audioEl.currentTime; }}
              onloadedmetadata={() => { if (audioEl) playerDuration = audioEl.duration; }}
              onplay={() => playerPlaying = true}
              onpause={() => playerPlaying = false}
              onended={() => playerPlaying = false}
              class="hidden"
            ></audio>

            <!-- Player controls -->
            <div class="bg-slate-950/80 border border-slate-800 rounded-2xl p-6 space-y-4 relative overflow-hidden">
              <div class="absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent pointer-events-none"></div>

              <!-- Current chapter label -->
              <div class="text-center min-h-[1.5rem]">
                {#if audiobookChapters.length > 0 && currentChapterIndex >= 0}
                  <p class="text-xs font-bold text-emerald-400 uppercase tracking-widest truncate">
                    {audiobookChapters[currentChapterIndex].title}
                  </p>
                {:else}
                  <p class="text-xs text-slate-600 uppercase tracking-widest">—</p>
                {/if}
              </div>

              <!-- Progress bar -->
              <div class="space-y-1">
                <input
                  type="range" min="0" max={playerDuration || 100} step="1"
                  value={playerCurrentTime}
                  onmousedown={() => playerSeeking = true}
                  oninput={(e) => { playerCurrentTime = Number((e.target as HTMLInputElement).value); }}
                  onchange={(e) => { if (audioEl) audioEl.currentTime = Number((e.target as HTMLInputElement).value); playerSeeking = false; }}
                  class="w-full h-1.5 rounded-full accent-emerald-500 cursor-pointer bg-slate-800"
                />
                <div class="flex justify-between text-[10px] font-mono text-slate-500">
                  <span>{formatTime(playerCurrentTime)}</span>
                  <span>{formatTime(playerDuration)}</span>
                </div>
              </div>

              <!-- Play/Pause + skip -->
              <div class="flex items-center justify-center gap-6">
                <button
                  onclick={() => { const i = currentChapterIndex; if (i > 0) seekToChapter(audiobookChapters[i-1]); }}
                  class="text-slate-400 hover:text-white transition-colors"
                  title="Capitolo precedente"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="19 20 9 12 19 4 19 20"/><line x1="5" y1="19" x2="5" y2="5"/></svg>
                </button>
                <button
                  onclick={() => { if (!audioEl) return; playerPlaying ? audioEl.pause() : audioEl.play(); }}
                  class="w-14 h-14 rounded-full bg-emerald-500 hover:bg-emerald-400 text-white flex items-center justify-center shadow-lg shadow-emerald-500/30 transition-all active:scale-95"
                >
                  {#if playerPlaying}
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="10" y1="4" x2="10" y2="20"/><line x1="14" y1="4" x2="14" y2="20"/></svg>
                  {:else}
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="translate-x-0.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                  {/if}
                </button>
                <button
                  onclick={() => { const i = currentChapterIndex; if (i < audiobookChapters.length - 1) seekToChapter(audiobookChapters[i+1]); }}
                  class="text-slate-400 hover:text-white transition-colors"
                  title="Capitolo successivo"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/></svg>
                </button>
              </div>
            </div>

            <!-- Chapter list -->
            {#if audiobookChapters.length > 0}
              <div class="space-y-2">
                <p class="text-[10px] font-black text-slate-500 uppercase tracking-widest">Capitoli ({audiobookChapters.length})</p>
                <div class="max-h-[320px] overflow-y-auto pr-1 custom-scrollbar space-y-1">
                  {#each audiobookChapters as chapter, i}
                    {@const isActive = i === currentChapterIndex}
                    <button
                      onclick={() => seekToChapter(chapter)}
                      class="w-full flex items-center justify-between px-4 py-3 rounded-xl transition-all text-left
                        {isActive
                          ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-300'
                          : 'bg-slate-900/30 border border-white/5 hover:bg-white/5 text-slate-300'}"
                    >
                      <div class="flex items-center gap-3 min-w-0">
                        <span class="text-[10px] font-mono {isActive ? 'text-emerald-500' : 'text-slate-600'} shrink-0">{String(i+1).padStart(2,'0')}</span>
                        <span class="text-xs font-medium truncate">{chapter.title}</span>
                      </div>
                      <span class="text-[10px] font-mono {isActive ? 'text-emerald-500' : 'text-slate-500'} shrink-0 ml-3">{formatTime(chapter.start_ms / 1000)}</span>
                    </button>
                  {/each}
                </div>
              </div>
            {/if}

            <!-- Download -->
            <div class="flex justify-center pt-2">
              <a href={audioSrc} download
                class="px-8 py-3 rounded-2xl bg-white/5 border border-white/10 hover:bg-white/10 text-white text-xs font-black uppercase tracking-widest transition-all flex items-center gap-2"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
                Download Master File
              </a>
            </div>
          </div>
        {:else}
          <div class="py-24 text-center rounded-3xl border border-dashed border-slate-800 bg-slate-900/20 space-y-6">
              <div class="flex justify-center">
                  <div class="w-16 h-16 rounded-full bg-slate-800/50 flex items-center justify-center text-slate-600">
                      <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 10v3"/><path d="M6 6v11"/><path d="M10 3v18"/><path d="M14 8v7"/><path d="M18 5v13"/><path d="M22 10v3"/></svg>
                  </div>
              </div>
              <div class="space-y-1">
                  <h3 class="text-xl font-black text-white italic uppercase tracking-tighter">Mastering not ready</h3>
                  <p class="text-slate-500 text-sm max-w-sm mx-auto">
                    Il file audiolibro finale verrà generato automaticamente al termine della produzione vocale (Stage D).
                  </p>
              </div>
              
              {#if project.status === 'completed' && !project.audiobook}
                 <button 
                   onclick={handleTriggerMaster}
                   class="px-8 py-3 rounded-2xl bg-emerald-500 hover:bg-emerald-400 text-white font-black uppercase tracking-widest shadow-lg shadow-emerald-500/20"
                 >
                    Innesca Fase F Manualmente
                 </button>
              {/if}
          </div>
        {/if}
      </div>
    {/if}
  {/if}
</div>

<style>
  .custom-scrollbar::-webkit-scrollbar { width: 4px; }
  .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
  .custom-scrollbar::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 10px; }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #334155; }
</style>
