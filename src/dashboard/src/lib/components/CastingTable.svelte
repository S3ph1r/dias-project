<script lang="ts">
  import type { Fingerprint, PreproductionData } from '../api';
  import { savePreproduction } from '../api';

  interface Props {
    projectId: string;
    fingerprint: Fingerprint;
    preproduction: PreproductionData;
    voices: Record<string, any>; // Cambiato da string[] a Record
    globalVoice: string | null;
    onSaved?: () => void;
  }

  let { projectId, fingerprint, preproduction, voices, globalVoice, onSaved }: Props = $props();

  // Helper per ottenere l'elenco degli ID vociali ordinati
  const voiceIds = $derived(Object.keys(voices).sort());
  
  // Helper per formattare la label della voce
  const getVoiceLabel = (id: string) => {
    const v = voices[id];
    if (!v || v.status === 'legacy') return id.toUpperCase();
    const meta = v.metadata || {};
    const spec = v.spec || {};
    return `${v.name} (${spec.gender || '?'}, ${spec.tone || '?'})`;
  };

  let castingDraft = $state<Record<string, string>>({});
  let paletteDraft = $state<string | undefined>(undefined);
  let saving = $state(false);

  // Inizializzazione sicura (solo se non ancora popolato)
  $effect(() => {
    // 1. Popola i nomi se la bozza è vuota e abbiamo i personaggi
    if (Object.keys(castingDraft).length === 0 && fingerprint?.casting?.characters) {
      const initial: Record<string, string> = {};
      fingerprint.casting.characters.forEach(char => {
        initial[char.name] = preproduction.casting[char.name] || "";
      });
      castingDraft = initial;
    }
    
    // 2. Sincronizza Palette solo se non definita
    if (paletteDraft === undefined && preproduction.palette_choice) {
      paletteDraft = preproduction.palette_choice;
    }
  });

  const handleSave = async () => {
    console.log("💾 TENTATIVO SALVATAGGIO...", { castingDraft, paletteDraft, globalVoice });
    saving = true;
    try {
      // Converte iProxy di Svelte 5 in un oggetto piano per la serializzazione JSON
      const castingData = JSON.parse(JSON.stringify(castingDraft));
      
      const payload = {
        ...preproduction,
        casting: castingData,
        palette_choice: paletteDraft,
        global_voice: globalVoice || undefined
      };
      
      console.log("📤 PAYLOAD PRONTO:", payload);
      
      await savePreproduction(projectId, payload);
      
      console.log("✅ SALVATAGGIO COMPLETATO!");
      alert('Configurazione Pre-produzione salvata con successo!');
      if (onSaved) onSaved();
    } catch (e) {
      console.error("❌ ERRORE SALVATAGGIO:", e);
      alert(`Errore critico durante il salvataggio: ${(e as Error).message}`);
    } finally {
      saving = false;
    }
  };

  const roleColors = {
    primary: 'text-sky-400 bg-sky-400/10 border-sky-400/20',
    secondary: 'text-violet-400 bg-violet-400/10 border-violet-400/20',
    tactical: 'text-slate-400 bg-slate-400/10 border-slate-400/20'
  };
</script>

<div class="space-y-6 pb-12">


  <!-- SOUNDTRACK & MOOD SELECTION -->
  <div class="space-y-4">
    <div class="flex items-center gap-2">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="text-emerald-400"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
      <h4 class="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">Soundtrack & Atmosphere Palette</h4>
    </div>
    
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      {#each fingerprint.sound_design.palette_proposals as palette}
        <button 
          onclick={() => paletteDraft = palette.name}
          class="text-left p-5 rounded-2xl border transition-all space-y-3 group relative overflow-hidden
            {paletteDraft === palette.name 
              ? 'bg-emerald-500/10 border-emerald-500/40 shadow-xl shadow-emerald-500/5' 
              : 'bg-slate-900/40 border-slate-800 hover:border-slate-700'}"
        >
          {#if paletteDraft === palette.name}
            <div class="absolute top-0 right-0 p-3">
              <div class="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_10px_#10b981]"></div>
            </div>
          {/if}
          
          <div class="space-y-1">
            <p class="text-sm font-black {paletteDraft === palette.name ? 'text-emerald-300' : 'text-slate-200'}">{palette.name}</p>
            <p class="text-[10px] text-slate-500 font-medium leading-relaxed">{palette.description}</p>
          </div>
          <div class="pt-2 border-t border-slate-800/50">
            <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest">Suitability</p>
            <p class="text-[10px] text-slate-500 italic mt-1">{palette.suitability}</p>
          </div>
        </button>
      {/each}
    </div>
  </div>

  <!-- CHARACTER CASTING TABLE -->
  <div class="space-y-4 pt-4">
    <div class="flex items-center gap-2">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="text-sky-400"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
      <h4 class="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">Character Casting Dossier</h4>
    </div>

    <div class="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/40 backdrop-blur-xl">
      <table class="w-full text-left border-collapse">
        <thead>
          <tr class="bg-slate-950/50 border-b border-slate-800">
            <th class="px-6 py-4 text-[9px] font-black text-slate-500 uppercase tracking-widest">Character</th>
            <th class="px-6 py-4 text-[9px] font-black text-slate-500 uppercase tracking-widest text-center">IA Profile / Traits</th>
            <th class="px-6 py-4 text-[9px] font-black text-slate-500 uppercase tracking-widest w-64 text-right">Voice Selection</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-800/50">
          {#each preproduction.characters_dossier as char}
            <tr class="hover:bg-slate-800/20 transition-colors group">
              <td class="px-6 py-5 align-top">
                <div class="flex flex-col gap-1.5">
                  <span class="text-sm font-black text-white group-hover:text-sky-400 transition-colors">{char.name}</span>
                  <span class="inline-flex items-center w-fit px-2 py-0.5 rounded-full border text-[8px] font-black uppercase tracking-wider {roleColors[char.role_category] || roleColors.secondary}">
                    {char.role_category}
                  </span>
                </div>
              </td>
              <td class="px-6 py-5 align-top">
                <div class="space-y-2 max-w-xl">
                  <p class="text-xs text-slate-400 leading-relaxed">
                    <span class="text-slate-600 font-bold uppercase text-[9px] tracking-tight block mb-0.5">Role Description</span>
                    {char.role_description}
                  </p>
                  <div class="flex gap-4 pt-1">
                    <div class="flex-1">
                      <span class="text-[9px] font-black text-slate-600 uppercase tracking-widest block">Acoustic identity</span>
                      <span class="text-[10px] text-slate-300 italic font-medium">"{char.vocal_profile}"</span>
                    </div>
                  </div>
                </div>
              </td>
              <td class="px-6 py-5 align-top text-right">
                <select 
                  bind:value={castingDraft[char.name]}
                  class="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-slate-300 focus:border-sky-500 outline-none transition-all shadow-inner font-bold"
                >
                  <option value={undefined}>Seleziona Voce...</option>
                  {#each voiceIds as vid}
                    {@const v = voices[vid]}
                    <option value={vid}>
                      {getVoiceLabel(vid)}
                    </option>
                  {/each}
                </select>
                  {#if castingDraft[char.name] && voices[castingDraft[char.name]]?.metadata?.description}
                    <p class="text-[9px] text-slate-500 px-1 text-right italic max-w-[200px] truncate" title={voices[castingDraft[char.name]].metadata.description}>
                      {voices[castingDraft[char.name]].metadata.description}
                    </p>
                  {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  <!-- FINAL ACTIONS -->
  <div class="flex justify-center pt-8 border-t border-slate-800/50">
    <button 
      onclick={handleSave}
      disabled={saving}
      class="px-12 py-4 rounded-2xl bg-sky-500 hover:bg-sky-400 text-white text-sm font-black uppercase tracking-widest transition-all active:scale-95 disabled:opacity-50 shadow-2xl shadow-sky-500/40"
    >
      {saving ? 'Salvataggio in corso...' : '💾 Salva Configurazione Pre-produzione'}
    </button>
  </div>
</div>
