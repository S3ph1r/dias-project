<script lang="ts">
  import { onMount, tick } from 'svelte';

  interface Props {
    voices: Record<string, any>;
    selectedVoice: string | null;
    onSelect: (id: string) => void;
  }

  let { voices, selectedVoice, onSelect }: Props = $props();

  const voiceIds = $derived(Object.keys(voices).sort());
  
  // local active state if no selectedVoice initially
  let localActiveIndex = $state(0);
  
  const activeIndex = $derived.by(() => {
    if (selectedVoice) {
      const idx = voiceIds.indexOf(selectedVoice);
      return idx >= 0 ? idx : 0;
    }
    return localActiveIndex;
  });

  let isScrolling = false;
  let audio: HTMLAudioElement | null = null;
  let playingVoiceId = $state<string | null>(null);
  let isPlaying = $state(false);

  const stopAudio = () => {
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
    }
    isPlaying = false;
    playingVoiceId = null;
  };

  const navigate = (dir: number) => {
    if (isScrolling) return;
    
    // Stop audio on scroll
    stopAudio();

    let next = activeIndex + dir;
    if (next < 0) next = voiceIds.length - 1;
    if (next >= voiceIds.length) next = 0;
    
    onSelect(voiceIds[next]);
    
    isScrolling = true;
    setTimeout(() => { isScrolling = false; }, 400); // Wait for transition
  };

  const handleWheel = (e: WheelEvent) => {
    e.preventDefault();
    if (Math.abs(e.deltaY) > 8) {
      navigate(e.deltaY > 0 ? 1 : -1);
    }
  };

  const handlePlayPreview = (id: string) => {
    // Toggle if same voice
    if (playingVoiceId === id && isPlaying) {
      stopAudio();
      return;
    }

    // Stop previous
    stopAudio();

    const v = voices[id];
    if (v?.sample_url) {
      audio = new Audio(v.sample_url);
      playingVoiceId = id;
      isPlaying = true;
      
      audio.play().catch(e => {
        console.error('Playback failed:', e);
        stopAudio();
      });

      audio.onended = () => {
        stopAudio();
      };
    }
  };

  // Helper for 3D positioning
  const getCardStyle = (i: number) => {
    const count = voiceIds.length;
    let diff = i - activeIndex;
    
    // Virtual wrap-around for short lists
    if (diff > count / 2) diff -= count;
    if (diff < -count / 2) diff += count;

    const absDiff = Math.abs(diff);
    
    // 3D parameters
    const rotateY = diff * -45; // Orientation in the ring
    const translateX = diff * 220; // Lateral spread
    const translateZ = absDiff === 0 ? 50 : -200 - (absDiff * 50); // Depth
    const opacity = 1 - (absDiff * 0.4);
    const scale = 1 - (absDiff * 0.15);
    const zIndex = 100 - absDiff;

    return `
      transform: perspective(1000px) rotateY(${rotateY}deg) translateX(${translateX}px) translateZ(${translateZ}px) scale(${scale});
      opacity: ${opacity};
      z-index: ${zIndex};
      visibility: ${absDiff > 2 ? 'hidden' : 'visible'};
    `;
  };
</script>

<div 
  onwheel={handleWheel}
  class="relative h-[320px] w-full flex items-center justify-center select-none overflow-hidden"
>
  <!-- Background Aura (Larger for 3D) -->
  <div class="absolute inset-0 flex items-center justify-center opacity-30 pointer-events-none">
    <div class="w-[500px] h-[500px] bg-sky-500 rounded-full blur-[150px] animate-pulse"></div>
  </div>

  <div class="relative w-full h-full flex items-center justify-center">
    {#each voiceIds as vid, i (vid)}
      {@const v = voices[vid]}
      <div 
        class="absolute w-[360px] min-h-[220px] transition-all duration-[600ms] cubic-bezier(0.23, 1, 0.32, 1)"
        style={getCardStyle(i)}
      >
        <div class="p-8 rounded-[2rem] bg-slate-900/90 backdrop-blur-2xl border {i === activeIndex ? 'border-sky-400/40 shadow-[0_0_60px_rgba(56,189,248,0.2)]' : 'border-slate-800 shadow-xl'} relative overflow-hidden group h-full">
           <!-- Active Accent -->
           {#if i === activeIndex}
             <div class="absolute -top-12 -right-12 w-32 h-32 bg-sky-500/10 rounded-full blur-3xl"></div>
           {/if}

           <div class="relative z-10 space-y-5">
             <div class="flex items-start justify-between">
               <div class="space-y-0.5">
                 <span class="text-[8px] font-black text-sky-500 uppercase tracking-[0.3em] block">ARIA Identity</span>
                 <h3 class="text-xl font-black text-white tracking-tight italic">{v.name || vid}</h3>
               </div>
               
               <button 
                 onclick={() => handlePlayPreview(vid)}
                 class="w-10 h-10 rounded-full bg-sky-500 text-white flex items-center justify-center shadow-lg transition-all active:scale-90"
               >
                 {#if playingVoiceId === vid && isPlaying}
                   <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12"/></svg>
                 {:else}
                   <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                 {/if}
               </button>
             </div>

             <!-- Metadata Condensed -->
             <div class="flex gap-6 mt-1">
               <div class="space-y-0.5">
                 <span class="text-[7px] font-bold text-slate-500 uppercase tracking-widest">Type</span>
                 <p class="text-[10px] text-slate-200 font-bold">{v.spec?.gender || 'Neutral'}, {v.spec?.age_range || '?'}</p>
               </div>
               <div class="space-y-0.5">
                 <span class="text-[7px] font-bold text-slate-500 uppercase tracking-widest">Signal</span>
                 <p class="text-[10px] text-slate-200 font-bold uppercase">{v.spec?.language || 'it-IT'}</p>
               </div>
             </div>

             <!-- Traits -->
             <div class="space-y-2">
                <div class="flex flex-wrap gap-1.5">
                  {#each (v.spec?.style || '').split(',').map(s => s.trim()) as trait}
                    {#if trait}
                      <span class="px-2 py-0.5 rounded-md bg-slate-800/80 text-[8px] font-black text-slate-400 border border-slate-700 uppercase tracking-wider">{trait}</span>
                    {/if}
                  {/each}
                </div>
                <!-- Only show full description for active card -->
                {#if i === activeIndex}
                  <p class="text-[9px] text-slate-400 italic leading-relaxed line-clamp-2 transition-all opacity-100">
                    {v.metadata?.description || 'Synchronizing vocal profile...'}
                  </p>
                {/if}
             </div>
           </div>
        </div>
      </div>
    {/each}
  </div>

  <!-- Pagination Glow Dots -->
  <div class="absolute bottom-6 flex gap-2">
    {#each voiceIds as vid, i}
      <button 
        onclick={() => onSelect(vid)}
        class="w-1 h-1 rounded-full transition-all duration-500 {i === activeIndex ? 'bg-sky-400 w-6 shadow-[0_0_12px_#38bdf8]' : 'bg-slate-800'}"
      ></button>
    {/each}
  </div>
</div>

<style>
  .custom-transition {
    transition-timing-function: cubic-bezier(0.23, 1, 0.32, 1);
  }
</style>
