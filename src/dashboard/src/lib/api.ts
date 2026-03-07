// Simple implementation of the DIAS API client
const API_BASE = "http://192.168.1.201:8000";

export interface Project {
    id: string;
    name: string;
    last_modified: string;
}

export interface AriaNode {
    hostname: string;
    status: string;
    platform: string;
    available_voices: string[];
}

export async function fetchProjects(): Promise<Project[]> {
    const res = await fetch(`${API_BASE}/projects`);
    if (!res.ok) throw new Error("Failed to fetch projects");
    return res.json();
}

export async function fetchProjectStatus(id: string) {
    const res = await fetch(`${API_BASE}/projects/${id}`);
    if (!res.ok) throw new Error("Failed to fetch project status");
    return res.json();
}

export async function fetchAriaNodes(): Promise<AriaNode[]> {
    const res = await fetch(`${API_BASE}/aria/nodes`);
    if (!res.ok) throw new Error("Failed to fetch ARIA nodes");
    return res.json();
}

export async function fetchVoices() {
    const res = await fetch(`${API_BASE}/info/voices`);
    if (!res.ok) throw new Error("Failed to fetch voices");
    return res.json();
}
