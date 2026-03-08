<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { fetchProjectDetails, pushSceneToStageD, fetchVoices, resumePipeline, resetStage, type Project, type ProjectStage } from '../../../lib/api';

  let project = $state<Project | null>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let processingScene = $state<string | null>(null);
  let voices = $state<string[]>([]);
  let selectedVoice = $state<string | null>(null);
  let resetting = $state<string | null>(null);
  let resuming = $state(false);

  const loadData = async () => {
    try {
      const [details, voiceData] = await Promise.all([
        fetchProjectDetails(page.params.id),
        fetchVoices()
      ]);
      project = details;
      voices = voiceData.voices;
      if (voices.length > 0 && !selectedVoice) {
        selectedVoice = voices[0];
      }
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  };

  onMount(loadData);

  const handlePushScene = async (projectId: string, sceneFile: string) => {
    processingScene = sceneFile;
    try {
      await pushSceneToStageD(projectId, sceneFile, selectedVoice || undefined);
      alert(`Scene ${sceneFile} pushed with voice ${selectedVoice || 'default'} successfully!`);
      // Optional: Refresh data after push
      await loadData();
    } catch (e) {
      alert(`Error: ${(e as Error).message}`);
    } finally {
      processingScene = null;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'done': return 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20';
      case 'in_progress': return 'text-sky-400 bg-sky-400/10 border-sky-400/20';
      default: return 'text-slate-500 bg-slate-500/10 border-slate-500/20';
    }
  };
  const handleResumePipeline = async () => {
    if (!project) return;
    resuming = true;
    try {
      const result = await resumePipeline(project.id);
      alert(`Pipeline resumed! Pushed ${result.pushed_count} missing tasks.`);
      await loadData();
    } catch (e) {
      alert(`Error: ${(e as Error).message}`);
    } finally {
      resuming = false;
    }
  };

  const handleResetStage = async (stageId: string) => {
    if (!project) return;
    const confirmed = confirm(`SEI SICURO? Questa azione cancellerà tutti i file dello ${stageId} per questo progetto e li rimetterà in coda dallo stage precedente.`);
    if (!confirmed) return;

    resetting = stageId;
    try {
      await resetStage(project.id, stageId);
      alert(`Stage ${stageId} resettato con successo.`);
      await loadData();
    } catch (e) {
      alert(`Error: ${(e as Error).message}`);
    } finally {
      resetting = null;
    }
  };
</script>

<div class="px-8 py-10 max-w-7xl mx-auto space-y-12">
  <header class="space-y-4">
    <div class="flex items-center gap-4">
       <a href="/" class="p-2 rounded-lg bg-slate-900 border border-slate-800 hover:bg-slate-800 transition-colors">
         <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-5 h-5"><path d="m15 18-6-6 6-6"/></svg>
       </a>
       <div class="h-px flex-1 bg-slate-800"></div>
    </div>
    <div class="flex justify-between items-end">
      <div class="space-y-1">
        <h2 class="text-5xl font-black tracking-tighter uppercase italic">{project?.name || 'Project Detail'}</h2>
        <p class="text-slate-400 font-mono text-sm tracking-widest">{project?.id || '...'}</p>
      </div>
      <div class="flex items-center gap-6">
        {#if project?.overall_progress < 100}
            <button 
                onclick={handleResumePipeline}
                disabled={resuming}
                class="px-6 py-3 rounded-2xl bg-sky-500 hover:bg-sky-400 text-white font-black uppercase tracking-widest transition-all active:scale-95 disabled:opacity-50 flex items-center gap-3 shadow-lg shadow-sky-500/20"
            >
                {#if resuming}
                    <div class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                    Resuming...
                {:else}
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m5 3 14 9-14 9V3z"/></svg>
                    Resume Pipeline
                {/if}
            </button>
        {:else}
            <div class="px-6 py-3 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-black uppercase tracking-widest flex items-center gap-3">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                Completed
            </div>
        {/if}
        <div class="text-right space-y-2">
            <p class="text-xs font-bold text-slate-500 uppercase tracking-widest">Total Progress</p>
            <p class="text-4xl font-black text-sky-400">{project?.overall_progress || 0}%</p>
        </div>
      </div>
    </div>
  </header>

  {#if loading}
    <div class="space-y-8 animate-pulse">
      <div class="h-48 bg-slate-900/50 rounded-3xl border border-slate-800"></div>
      <div class="h-48 bg-slate-900/50 rounded-3xl border border-slate-800"></div>
    </div>
  {:else if error}
    <div class="p-8 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 font-medium">
      {error}
    </div>
  {:else if project}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
      {#each project.stages as stage}
        <div class="bg-slate-900/40 backdrop-blur-xl border border-slate-800 rounded-3xl p-8 space-y-6 flex flex-col {stage.is_placeholder ? 'opacity-40 grayscale pointer-events-none' : ''}">
          <div class="flex justify-between items-start">
            <div class="space-y-1">
              <p class="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">{stage.id}</p>
              <h3 class="text-2xl font-black text-white">{stage.name}</h3>
            </div>
            <div class="flex items-center gap-3">
               <button 
                onclick={() => handleResetStage(stage.id)}
                disabled={resetting === stage.id}
                title="Reset/Retry this stage"
                class="p-2 rounded-xl bg-rose-500/10 text-rose-500 border border-rose-500/20 hover:bg-rose-500/20 transition-all active:scale-95 disabled:opacity-50"
               >
                 <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" class={resetting === stage.id ? 'animate-spin' : ''}><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>
               </button>
               <span class="px-3 py-1 rounded-full border text-[10px] font-black uppercase tracking-wider {getStatusColor(stage.status)}">
                 {stage.status.replace('_', ' ')}
               </span>
            </div>
          </div>

          <div class="flex-1 overflow-hidden space-y-4">
            {#if stage.id === 'stage_d'}
              <div class="space-y-3">
                <p class="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">Select Voice Override</p>
                <div class="flex flex-wrap gap-2">
                  {#each voices as voice}
                    <button 
                      onclick={() => selectedVoice = voice}
                      class="px-4 py-2 rounded-xl text-xs font-bold transition-all border {selectedVoice === voice ? 'bg-sky-500 text-white border-sky-400 shadow-lg shadow-sky-500/20 scale-105' : 'bg-slate-950/50 text-slate-400 border-slate-800 hover:border-slate-700'}"
                    >
                      {voice}
                    </button>
                  {:else}
                    <p class="text-[10px] text-slate-600 italic">No voices detected from ARIA nodes.</p>
                  {/each}
                </div>
              </div>
            {/if}

            <p class="text-xs font-bold text-slate-500 uppercase tracking-widest">Produced Assets ({stage.files.length})</p>
            <div class="max-h-[300px] overflow-y-auto space-y-2 pr-2 custom-scrollbar">
              {#each stage.files as file}
                <div class="group flex items-center justify-between p-3 rounded-xl bg-slate-950/50 border border-slate-800 hover:border-slate-700 transition-all">
                  <span class="text-xs font-mono text-slate-300 truncate flex-1">{file}</span>
                  
                  {#if stage.id === 'stage_c'}
                    <button 
                      onclick={() => handlePushScene(project.id, file)}
                      disabled={processingScene === file}
                      class="ml-4 px-3 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-white text-[10px] font-black uppercase tracking-widest transition-all active:scale-95 disabled:opacity-50"
                    >
                      {processingScene === file ? 'Pushing...' : 'Push to Stage D'}
                    </button>
                  {/if}
                  
                  {#if stage.id === 'stage_d' && file.endsWith('.wav')}
                    <div class="ml-4 flex gap-2">
                       <button class="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-all">
                         <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                       </button>
                    </div>
                  {/if}
                </div>
              {:else}
                <p class="text-slate-600 text-xs italic">No assets produced yet.</p>
              {/each}
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .custom-scrollbar::-webkit-scrollbar {
    width: 4px;
  }
  .custom-scrollbar::-webkit-scrollbar-track {
    background: transparent;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: #1e293b;
    border-radius: 10px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: #334155;
  }
</style>
