<script>
  import { onMount } from 'svelte';
  import { slide, fade } from 'svelte/transition';
  import { fetchQuota, API_BASE } from '$lib/api';
  import { base } from '$app/paths';
  import { player } from '$lib/player.svelte';
  import "../app.css";
  
  let { children } = $props();
  let quota = $state({ usage: 0, limit: 20 });
  
  onMount(async () => {
    try {
      const data = await fetchQuota();
      quota = data;
    } catch (e) {
      console.error("Failed to fetch quota", e);
    }
    
    // Refresh quota every 30s
    const interval = setInterval(async () => {
      try {
        quota = await fetchQuota();
      } catch (e) {}
    }, 30000);
    
    return () => clearInterval(interval);
  });
</script>

<div class="flex h-screen bg-slate-950 text-slate-100 overflow-hidden">
  <!-- Sidebar -->
  <aside class="w-64 bg-slate-900 border-r border-slate-800 flex flex-col">
    <div class="p-6 border-b border-slate-800 flex items-center gap-3">
      <div class="w-8 h-8 bg-sky-500 rounded-lg flex items-center justify-center font-bold text-white shadow-lg shadow-sky-500/20">D</div>
      <h1 class="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">DIAS</h1>
    </div>
    
    <nav class="flex-1 p-4 space-y-2 overflow-y-auto">
      <a href="{base}/" class="flex items-center gap-3 px-4 py-3 rounded-xl bg-slate-800 text-sky-400 font-medium transition-all group">
        <span class="w-2 h-2 rounded-full bg-sky-500 shadow-[0_0_8px_rgba(14,165,233,0.8)]"></span>
        Dashboard
      </a>
      <a href="{base}/projects" class="flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-800/50 text-slate-400 hover:text-white transition-all">
        Progetti
      </a>
      <a href="{base}/aria" class="flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-800/50 text-slate-400 hover:text-white transition-all">
        ARIA Nodes
      </a>
    </nav>
    
    <div class="p-4 border-t border-slate-800 space-y-4">
      <!-- Gemini Quota -->
      <div class="px-4 py-3 rounded-xl bg-slate-900/50 border border-slate-800 space-y-2">
        <div class="flex justify-between items-center">
            <span class="text-[10px] font-black text-slate-500 uppercase tracking-widest">Gemini Quota</span>
            <span class="text-[10px] font-black {quota.usage >= quota.limit ? 'text-rose-500' : 'text-sky-400'}">{quota.usage}/{quota.limit}</span>
        </div>
        <div class="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
            <div 
                class="h-full {quota.usage >= quota.limit ? 'bg-rose-500' : 'bg-sky-500'} transition-all duration-500" 
                style="width: {Math.min(100, (quota.usage / quota.limit) * 100)}%"
            ></div>
        </div>
      </div>

      <div class="flex items-center gap-3 px-4 py-3 rounded-xl bg-slate-800/30 border border-slate-800">
        <div class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
        <span class="text-xs font-medium text-slate-400 uppercase tracking-wider">System Online</span>
      </div>
    </div>
  </aside>

  <!-- Main Content -->
  <main class="flex-1 overflow-y-auto bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-slate-950 pb-24">
    {@render children()}
  </main>

  <!-- Persistent Audio Player Bar -->
  {#if player.currentWavUrl}
    <div class="fixed bottom-0 left-64 right-0 h-20 bg-slate-900/80 backdrop-blur-xl border-t border-slate-800 px-8 flex items-center justify-between z-50 animate-in slide-in-from-bottom duration-300">
      <div class="flex items-center gap-4 w-1/3">
        <div class="w-12 h-12 rounded-xl bg-sky-500/20 border border-sky-500/30 flex items-center justify-center text-xl shadow-inner">
          🔊
        </div>
        <div class="min-w-0">
          <p class="text-[10px] font-black text-sky-400 uppercase tracking-widest mb-1">Now Playing</p>
          <p class="text-sm font-bold text-white truncate">{player.currentSceneId}</p>
        </div>
      </div>

      <div class="flex flex-col items-center gap-2 w-1/3">
        <div class="flex items-center gap-6">
           <button class="text-slate-500 hover:text-white transition-all"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="19 20 9 12 19 4 19 20"/><line x1="5" y1="19" x2="5" y2="5"/></svg></button>
           
           <button 
            onclick={() => player.isPlaying = !player.isPlaying}
            class="w-10 h-10 rounded-full bg-white text-slate-950 flex items-center justify-center hover:scale-110 active:scale-95 transition-all shadow-lg"
           >
             {#if player.isPlaying}
               <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="10" y1="4" x2="10" y2="20"/><line x1="14" y1="4" x2="14" y2="20"/></svg>
             {:else}
               <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" class="translate-x-0.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
             {/if}
           </button>

           <button class="text-slate-500 hover:text-white transition-all"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/></svg></button>
        </div>
      </div>

      <div class="w-1/3 flex justify-end gap-4 items-center">
        <audio 
          src={API_BASE + player.currentWavUrl} 
          bind:paused={player.paused}
          autoplay
          onplay={() => player.isPlaying = true}
          onpause={() => player.isPlaying = false}
          class="hidden"
        ></audio>
        <div class="flex items-center gap-2 group">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-slate-500"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
          <div class="w-24 h-1 bg-slate-800 rounded-full overflow-hidden">
             <div class="h-full bg-sky-500 w-2/3"></div>
          </div>
        </div>
      </div>
    </div>
  {/if}
</div>
