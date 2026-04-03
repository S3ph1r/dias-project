export interface PlayerState {
    currentSceneId: string | null;
    currentWavUrl: string | null;
    isPlaying: boolean;
}

export const player = $state<PlayerState>({
    currentSceneId: null,
    currentWavUrl: null,
    isPlaying: false
});

export function playScene(sceneId: string, wavUrl: string) {
    player.currentSceneId = sceneId;
    player.currentWavUrl = wavUrl;
    player.isPlaying = true;
}

export function togglePlayback() {
    player.isPlaying = !player.isPlaying;
}
