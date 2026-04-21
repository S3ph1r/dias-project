export interface ProjectStage {
    id: string;
    name: string;
    status: 'pending' | 'in_progress' | 'done';
    files: string[];
    is_placeholder?: boolean;
}

export interface Project {
    id: string;
    name: string;
    status: string;
    active_stage: string | null;
    last_modified: string;
    total_chunks?: number;
    overall_progress?: number;
    stages?: ProjectStage[];
    audiobook?: {
        url: string;
        filename: string;
        size: number;
        chapters_file?: string;
    };
}

export interface Scene {
    id: string;
    wav_url: string | null;
    text: string;
    instruct: string;
    voice: string;
}

export interface ChapterSummary {
    chunk_id: string;
    chunk_index: number;
    title: string;
    scenes: Scene[];
    scene_count: number;
    wav_count: number;
    status: 'pending' | 'scripted' | 'in_progress' | 'voice_done';
    progress_pct: number;
}

export interface AriaNode {
    hostname: string;
    status: 'online' | 'offline' | 'busy';
    platform: string;
    available_voices: string[];
}

export interface CharacterProfile {
    name: string;
    role_category: 'primary' | 'secondary' | 'tactical';
    role_description: string;
    traits: string;
    vocal_profile: string;
}

export interface ChapterFingerprint {
    id: string;
    title: string;
    summary: string;
}

export interface Fingerprint {
    metadata: {
        title: string;
        author: string;
        genre?: string;
        tone?: string;
    };
    chapters?: ChapterFingerprint[];
    chapters_list?: ChapterFingerprint[];
    casting?: {
        narrator: { vibe: string; style: string };
        characters: CharacterProfile[];
    };
}

export interface PreproductionData {
    casting: Record<string, string>;
    palette_choice?: string;
    global_voice?: string;
}

// base da $app/paths è il paths.base di svelte.config.js:
//   produzione (nginx /dias/): '/dias' → chiamate a /dias/projects, ecc.
//   local dev (porta 5173):    ''      → cade su VITE_API_BASE o localhost:8000
import { base } from '$app/paths';
import { browser } from '$app/environment';
export const API_BASE: string = base || (import.meta.env.VITE_API_BASE as string) || (browser ? `http://${window.location.hostname}:8000` : 'http://127.0.0.1:8000');

export async function fetchProjects(): Promise<Project[]> {
    const res = await fetch(`${API_BASE}/projects`);
    if (!res.ok) throw new Error('Failed to fetch projects');
    const data = await res.json();
    return data.map((p: any) => ({ ...p, id: p.project_id || p.id }));
}

export async function fetchProjectDetails(id: string): Promise<Project> {
    const res = await fetch(`${API_BASE}/projects/${id}`);
    if (!res.ok) throw new Error('Failed to fetch project details');
    const data = await res.json();
    return { ...data, id: data.project_id || data.id };
}

export async function pushSceneToStageD(projectId: string, sceneFile: string, voiceOverride?: string): Promise<{ status: string; message: string }> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/push_scene`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            scene_file: sceneFile,
            voice_override: voiceOverride
        })
    });
    if (!res.ok) throw new Error('Failed to push scene to Stage D');
    return res.json();
}

export async function fetchAriaNodes(): Promise<AriaNode[]> {
    const res = await fetch(`${API_BASE}/aria/nodes`);
    if (!res.ok) throw new Error('Failed to fetch ARIA nodes');
    return res.json();
}

export async function fetchVoices(): Promise<{ voices: Record<string, any> }> {
    const res = await fetch(`${API_BASE}/info/voices`);
    if (!res.ok) throw new Error('Failed to fetch voices');
    return res.json();
}

export async function fetchQuota(): Promise<{ usage: number; limit: number; available: number; reset_at: string }> {
    const res = await fetch(`${API_BASE}/info/quota`);
    if (!res.ok) throw new Error('Failed to fetch quota info');
    return res.json();
}

export async function resetStage(projectId: string, stageId: string): Promise<{ status: string; message: string }> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/stages/${stageId}`, {
        method: 'DELETE'
    });
    if (!res.ok) throw new Error('Failed to reset stage');
    return res.json();
}

export async function checkResume(projectId: string): Promise<{ status: string; voices: Record<string, number> }> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/resume/check`);
    if (!res.ok) throw new Error('Failed to check resume status');
    return res.json();
}

export async function resumePipeline(projectId: string, voiceOverride?: string): Promise<{ status: string; pushed_count: number }> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            voice_override: voiceOverride
        })
    });
    if (!res.ok) throw new Error('Failed to resume pipeline');
    return res.json();
}

export async function fetchChapters(projectId: string): Promise<ChapterSummary[]> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/chapters`);
    if (!res.ok) throw new Error('Failed to fetch chapters');
    return res.json();
}

export async function fetchSceneMetrics(projectId: string, sceneId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/scenes/${sceneId}/metrics`);
    if (!res.ok) throw new Error('Failed to fetch scene metrics');
    return res.json();
}

export async function retryScene(projectId: string, sceneId: string, instruct?: string): Promise<any> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/scenes/${sceneId}/retry`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruct })
    });
    if (!res.ok) throw new Error('Failed to retry scene');
    return res.json();
}

export async function fetchFingerprint(projectId: string): Promise<Fingerprint> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/fingerprint`);
    if (!res.ok) throw new Error('Failed to fetch fingerprint');
    return res.json();
}

export async function fetchPreproduction(projectId: string): Promise<PreproductionData> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/preproduction`);
    if (!res.ok) throw new Error('Failed to fetch pre-production data');
    return res.json();
}

export async function savePreproduction(projectId: string, data: PreproductionData): Promise<any> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/preproduction`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error('Failed to save pre-production data');
    return res.json();
}

export async function analyzeProject(projectId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/analyze`, {
        method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to start analysis');
    return res.json();
}

export async function fetchWorkerStatus(): Promise<{ workers: Record<string, 'running' | 'stopped'> }> {
    const res = await fetch(`${API_BASE}/system/workers`);
    if (!res.ok) throw new Error('Failed to fetch worker status');
    return res.json();
}
