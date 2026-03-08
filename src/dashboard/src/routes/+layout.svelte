<script>
  import { onMount } from 'svelte';
  import { fetchQuota } from '$lib/api';
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
      <a href="/" class="flex items-center gap-3 px-4 py-3 rounded-xl bg-slate-800 text-sky-400 font-medium transition-all group">
        <span class="w-2 h-2 rounded-full bg-sky-500 shadow-[0_0_8px_rgba(14,165,233,0.8)]"></span>
        Dashboard
      </a>
      <a href="/projects" class="flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-800/50 text-slate-400 hover:text-white transition-all">
        Progetti
      </a>
      <a href="/aria" class="flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-800/50 text-slate-400 hover:text-white transition-all">
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
  <main class="flex-1 overflow-y-auto bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-slate-950">
    {@render children()}
  </main>
</div>
