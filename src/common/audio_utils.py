import librosa
import numpy as np
import os
from pathlib import Path

def get_audio_metrics(file_path: str):
    """
    Calculate basic audio quality metrics for a WAV file.
    Returns a dictionary of metrics.
    """
    if not os.path.exists(file_path):
        return None
    
    try:
        y, sr = librosa.load(file_path, sr=22050)
        duration = librosa.get_duration(y=y, sr=sr)
        
        # 1. Pitch (Fundamental Frequency)
        f0, voiced_flag, _ = librosa.pyin(
            y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=sr
        )
        f0_voiced = f0[voiced_flag]
        pitch_mean = float(np.nanmean(f0_voiced)) if len(f0_voiced) > 0 else 0
        pitch_std = float(np.nanstd(f0_voiced)) if len(f0_voiced) > 0 else 0
        
        # 2. Energy (RMS)
        rms = librosa.feature.rms(y=y)[0]
        rms_mean = float(np.mean(rms))
        rms_max = float(np.max(rms))
        
        # 3. Spectral Centroid (Brightness)
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        centroid_mean = float(np.mean(centroid))
        
        # 4. Silence/Pauses
        # Detect non-silent intervals (top_db=30)
        intervals = librosa.effects.split(y, top_db=30)
        voiced_duration = sum([(end-start)/sr for start, end in intervals])
        silence_duration = duration - voiced_duration
        
        return {
            "duration_s": round(duration, 2),
            "pitch_avg_hz": round(pitch_mean, 1),
            "pitch_std_hz": round(pitch_std, 1),
            "rms_avg": round(rms_mean, 4),
            "rms_max": round(rms_max, 4),
            "brightness_avg_hz": round(centroid_mean, 1),
            "silence_ratio": round(silence_duration / duration, 2) if duration > 0 else 0,
            "quality_score": calculate_score(rms_mean, pitch_std, silence_duration / duration if duration > 0 else 0)
        }
    except Exception as e:
        print(f"Error analyzing {file_path}: {e}")
        return None

def calculate_score(rms, pitch_std, silence_ratio):
    """
    Heuristic scoring (0.0 to 1.0)
    """
    score = 1.0
    
    # Penalize very low volume
    if rms < 0.01: score -= 0.3
    
    # Penalize monotone voice (very low pitch deviation)
    if pitch_std < 5: score -= 0.2
    
    # Penalize too much silence (>40%)
    if silence_ratio > 0.4: score -= 0.2
    
    return max(0.1, round(score, 2))
