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
    last_modified: string;
    total_chunks?: number;
    overall_progress?: number;
    stages?: ProjectStage[];
}

export interface AriaNode {
    hostname: string;
    status: 'online' | 'offline' | 'busy';
    platform: string;
    available_voices: string[];
}

const API_BASE = 'http://192.168.1.201:8000';

export async function fetchProjects(): Promise<Project[]> {
    const res = await fetch(`${API_BASE}/projects`);
    if (!res.ok) throw new Error('Failed to fetch projects');
    return res.json();
}

export async function fetchProjectDetails(id: string): Promise<Project> {
    const res = await fetch(`${API_BASE}/projects/${id}`);
    if (!res.ok) throw new Error('Failed to fetch project details');
    return res.json();
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

export async function fetchVoices(): Promise<{ voices: string[] }> {
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

export async function resumePipeline(projectId: string): Promise<{ status: string; pushed_count: number }> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/resume`, {
        method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to resume pipeline');
    return res.json();
}
