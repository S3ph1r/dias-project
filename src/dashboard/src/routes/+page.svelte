<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchProjects, fetchAriaNodes, type Project, type AriaNode } from '$lib/api';

  let projects = $state<Project[]>([]);
  let ariaNodes = $state<AriaNode[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      const [pData, aData] = await Promise.all([
        fetchProjects(),
        fetchAriaNodes()
      ]);
      projects = pData;
      ariaNodes = aData;
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  });

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'bg-emerald-500 shadow-emerald-500/40';
      case 'stopped': return 'bg-rose-500 shadow-rose-500/40';
      case 'suspend': return 'bg-amber-500 shadow-amber-500/40';
      default: return 'bg-slate-500 shadow-slate-500/40';
    }
  };
</script>

<div class="px-8 py-10 max-w-7xl mx-auto space-y-12">
  <!-- Header Section -->
  <header class="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
    <div class="space-y-2">
      <h2 class="text-4xl font-extrabold tracking-tight">Project Overview</h2>
      <p class="text-slate-400 text-lg">Monitor and manage the immersive audiobook pipeline.</p>
    </div>
    <div class="flex gap-4">
      <button class="px-6 py-3 rounded-xl bg-sky-500 hover:bg-sky-400 text-white font-bold transition-all shadow-lg shadow-sky-500/25 active:scale-95">
        New Project
      </button>
      <button class="px-6 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-bold transition-all active:scale-95 border border-slate-700">
        Refresh
      </button>
    </div>
  </header>

  <!-- Status Grid -->
  <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
    <div class="bg-slate-900/40 backdrop-blur-xl border border-slate-800 p-6 rounded-2xl space-y-4">
      <p class="text-slate-500 font-bold uppercase text-xs tracking-widest">Active Projects</p>
      <p class="text-4xl font-black text-white">{projects.length}</p>
    </div>
    <div class="bg-slate-900/40 backdrop-blur-xl border border-slate-800 p-6 rounded-2xl space-y-4">
      <p class="text-slate-500 font-bold uppercase text-xs tracking-widest">ARIA Nodes</p>
      <p class="text-4xl font-black text-white">{ariaNodes.length}</p>
    </div>
    <div class="bg-slate-900/40 backdrop-blur-xl border border-slate-800 p-6 rounded-2xl space-y-4">
      <p class="text-slate-500 font-bold uppercase text-xs tracking-widest">Total Chunks</p>
      <p class="text-4xl font-black text-white">128</p>
    </div>
    <div class="bg-slate-900/40 backdrop-blur-xl border border-slate-800 p-6 rounded-2xl space-y-4">
      <p class="text-slate-500 font-bold uppercase text-xs tracking-widest">Time Saved</p>
      <p class="text-4xl font-black text-sky-400">42h</p>
    </div>
  </div>

  <!-- Projects List -->
  <section class="space-y-6">
    <div class="flex items-center gap-4">
      <h3 class="text-2xl font-bold">Recent Projects</h3>
      <div class="h-px flex-1 bg-slate-800"></div>
    </div>

    {#if loading}
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6 animate-pulse">
        <div class="h-48 bg-slate-900/50 rounded-2xl border border-slate-800"></div>
        <div class="h-48 bg-slate-900/50 rounded-2xl border border-slate-800"></div>
      </div>
    {:else if error}
      <div class="p-8 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 font-medium">
        Error loading data: {error}
      </div>
    {:else}
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        {#each projects as project}
          <a href="/projects/{project.id}" class="group bg-slate-900/40 backdrop-blur-xl border border-slate-800 hover:border-sky-500/50 p-8 rounded-3xl transition-all hover:translate-y-[-4px] relative overflow-hidden">
            <div class="absolute top-0 right-0 p-8">
              <div class="w-3 h-3 rounded-full {getStatusColor('running')} shadow-[0_0_12px_rgba(16,185,129,0.5)]"></div>
            </div>
            
            <div class="space-y-6 relative z-10">
              <div class="space-y-1">
                <h4 class="text-2xl font-black text-white group-hover:text-sky-400 transition-colors uppercase tracking-tight">{project.name}</h4>
                <p class="text-slate-500 text-sm font-medium">Last processed: {new Date(project.last_modified).toLocaleString()}</p>
              </div>

              <!-- Mini Progress -->
              <div class="space-y-3">
                 <div class="flex justify-between text-xs font-bold uppercase tracking-wider text-slate-400">
                   <span>Pipeline Completion</span>
                   <span class="text-sky-400">45%</span>
                 </div>
                 <div class="h-3 bg-slate-800 rounded-full overflow-hidden p-[2px]">
                   <div class="h-full bg-sky-500 rounded-full shadow-[0_0_12px_rgba(14,165,233,0.4)]" style="width: 45%;"></div>
                 </div>
              </div>
            </div>
            
            <!-- Bg glow -->
            <div class="absolute -bottom-12 -right-12 w-32 h-32 bg-sky-500/5 blur-[80px] group-hover:bg-sky-500/15 transition-all"></div>
          </a>
        {/each}
      </div>
    {/if}
  </section>

  <!-- ARIA Nodes -->
  <section class="space-y-6">
    <div class="flex items-center gap-4">
      <h3 class="text-2xl font-bold">Inference Nodes (ARIA)</h3>
      <div class="h-px flex-1 bg-slate-800"></div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
      {#each ariaNodes as node}
        <div class="bg-slate-900/40 backdrop-blur-xl border border-slate-800 p-6 rounded-2xl flex items-center gap-5 hover:bg-slate-800/20 transition-all">
          <div class="w-12 h-12 rounded-xl bg-slate-800 flex items-center justify-center text-2xl shadow-inner">
            {node.platform === 'windows' ? '🖥️' : '🐧'}
          </div>
          <div class="space-y-1">
            <p class="font-bold text-lg">{node.hostname}</p>
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full {getStatusColor(node.status)}"></span>
              <span class="text-xs uppercase font-bold text-slate-500">{node.status}</span>
            </div>
          </div>
        </div>
      {:else}
         <div class="col-span-full py-12 text-center bg-slate-900/20 rounded-2xl border border-dashed border-slate-800">
           <p class="text-slate-500 font-medium italic">No active nodes detected in the swarm.</p>
         </div>
      {/each}
    </div>
  </section>
</div>

<style>
  :global(body) {
    cursor: default;
  }
</style>
