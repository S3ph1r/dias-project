<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { fetchProjectDetails, pushSceneToStageD, type Project, type ProjectStage } from '../../../lib/api';

  let project = $state<Project | null>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let processingScene = $state<string | null>(null);

  const loadData = async () => {
    try {
      project = await fetchProjectDetails(page.params.id);
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
      await pushSceneToStageD(projectId, sceneFile);
      alert(`Scene ${sceneFile} pushed to Qwen3TTS successfully!`);
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
      <div class="text-right space-y-2">
        <p class="text-xs font-bold text-slate-500 uppercase tracking-widest">Total Progress</p>
        <p class="text-4xl font-black text-sky-400">{project?.overall_progress || 0}%</p>
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
            <span class="px-3 py-1 rounded-full border text-[10px] font-black uppercase tracking-wider {getStatusColor(stage.status)}">
              {stage.status.replace('_', ' ')}
            </span>
          </div>

          <div class="flex-1 overflow-hidden">
            <p class="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Produced Assets ({stage.files.length})</p>
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
