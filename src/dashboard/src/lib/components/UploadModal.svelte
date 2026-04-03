<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { fade, scale } from 'svelte/transition';
  import { API_BASE } from '../api';

  interface Props {
    show: boolean;
    onClose: () => void;
    onSuccess: (projectId: string) => void;
  }

  let { show, onClose, onSuccess }: Props = $props();

  let dragging = $state(false);
  let uploading = $state(false);
  let progress = $state(0);
  let fileInput = $state<HTMLInputElement | null>(null);

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    dragging = true;
  };

  const handleDragLeave = () => {
    dragging = false;
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    dragging = false;
    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
      uploadFile(files[0]);
    }
  };

  const handleFileSelect = (e: Event) => {
    const target = e.target as HTMLInputElement;
    if (target.files && target.files.length > 0) {
      uploadFile(target.files[0]);
    }
  };

  const uploadFile = async (file: File) => {
    if (!file.name.endsWith('.pdf') && !file.name.endsWith('.epub')) {
      alert('Solo file PDF o EPUB sono supportati.');
      return;
    }

    uploading = true;
    progress = 0;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${API_BASE}/projects/upload`, true);

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          progress = Math.round((e.loaded / e.total) * 100);
        }
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          const response = JSON.parse(xhr.responseText);
          onSuccess(response.project_id);
          onClose();
        } else {
          alert('Errore durante il caricamento del file.');
          uploading = false;
        }
      };

      xhr.onerror = () => {
        alert('Errore di connessione al server.');
        uploading = false;
      };

      xhr.send(formData);
    } catch (e) {
      console.error(e);
      uploading = false;
    }
  };
</script>

{#if show}
  <!-- Backdrop -->
  <div 
    class="fixed inset-0 z-50 flex items-center justify-center p-6 bg-slate-950/80 backdrop-blur-md"
    transition:fade={{ duration: 200 }}
    onclick={!uploading ? onClose : undefined}
  >
    <!-- Modal Content -->
    <div 
      class="w-full max-w-xl bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl overflow-hidden relative"
      transition:scale={{ duration: 300, start: 0.95 }}
      onclick={e => e.stopPropagation()}
    >
      <div class="p-8 space-y-6">
        <div class="flex items-center justify-between">
            <h3 class="text-2xl font-black uppercase tracking-tight">New Radiofilm</h3>
            <button onclick={onClose} class="text-slate-500 hover:text-white transition-colors">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
        </div>

        <!-- Drop Zone -->
        <div 
          class="aspect-video rounded-2xl border-2 border-dashed transition-all flex flex-col items-center justify-center gap-4 cursor-pointer relative overflow-hidden
                 {dragging ? 'border-sky-500 bg-sky-500/10 scale-[0.98]' : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'}"
          oncontextmenu={e => e.preventDefault()}
          ondragover={handleDragOver}
          ondragleave={handleDragLeave}
          ondrop={handleDrop}
          onclick={() => !uploading && fileInput?.click()}
        >
          <input 
            type="file" 
            bind:this={fileInput} 
            class="hidden" 
            accept=".pdf,.epub"
            onchange={handleFileSelect}
          />

          {#if uploading}
            <div class="flex flex-col items-center gap-4 w-full px-12">
               <div class="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                 <div class="h-full bg-sky-500 transition-all duration-300" style="width: {progress}%"></div>
               </div>
               <p class="text-xs font-black uppercase tracking-widest text-sky-400">Caricamento... {progress}%</p>
            </div>
          {:else}
            <div class="w-16 h-16 rounded-full bg-slate-900 flex items-center justify-center text-3xl shadow-xl">
              📚
            </div>
            <div class="text-center space-y-1">
              <p class="text-sm font-bold text-slate-200">Trascina il tuo PDF o EPUB qui</p>
              <p class="text-[10px] text-slate-500 font-medium uppercase tracking-widest">oppure clicca per sfogliare</p>
            </div>
          {/if}

          <!-- Glow -->
          <div class="absolute inset-0 bg-sky-500/5 pointer-events-none opacity-0 transition-opacity {dragging ? 'opacity-100' : ''}"></div>
        </div>

        <div class="bg-slate-950/50 p-4 rounded-xl border border-slate-800 flex items-start gap-3">
          <div class="text-amber-500 mt-0.5">⚠️</div>
          <p class="text-[10px] text-slate-500 leading-relaxed font-medium">
            Caricando un documento, avvierai automaticamente lo **Stage 0: Book Intelligence**. L'AI analizzerà i personaggi e la struttura del libro per preparare la tua sessione di casting.
          </p>
        </div>
      </div>
    </div>
  </div>
{/if}
