"""
claudius_blend.py — Blend spectral Jessica + SIWIS optimisé v3d
DTW vectorisé, blend spectral, gate silence, HF preserve.
~100ms pour 4s d'audio.
"""
import numpy as np
from scipy.ndimage import uniform_filter1d as smooth1d

SR = 22050
SEG_LEN = int(SR * 0.025)       # 25ms
N_MEL = 13
N_FFT = 2048
HOP = 512
WIN = np.hanning(N_FFT)
WIN_SQ = WIN ** 2

def _mel_features(audio, seg_len=SEG_LEN, n_bands=N_MEL):
    """Features mel-like vectorisées pour l'alignement DTW."""
    n_segs = len(audio) // seg_len
    if n_segs == 0:
        return np.zeros((1, n_bands))
    trimmed = audio[:n_segs * seg_len].reshape(n_segs, seg_len)
    specs = np.abs(np.fft.rfft(trimmed, axis=1)) ** 2
    n_freq = specs.shape[1]
    bsz = max(1, n_freq // n_bands)
    pad_len = bsz * n_bands - n_freq
    if pad_len > 0:
        specs = np.pad(specs, ((0, 0), (0, pad_len)))
    return specs[:, :bsz * n_bands].reshape(n_segs, n_bands, bsz).sum(axis=2)

def _dtw_cosine(fj, fs):
    """DTW avec distance cosine sur features spectrales."""
    nj, ns = fj.shape[0], fs.shape[0]
    # Normalisation cosine
    fj_n = fj / (np.linalg.norm(fj, axis=1, keepdims=True) + 1e-10)
    fs_n = fs / (np.linalg.norm(fs, axis=1, keepdims=True) + 1e-10)
    dist = 1.0 - fj_n @ fs_n.T
    
    # DTW - accès array plat pour rapidité
    cost = np.full((nj + 1, ns + 1), np.inf)
    cost[0, 0] = 0.0
    cost_flat = cost.ravel()
    stride = ns + 1
    for i in range(1, nj + 1):
        di = dist[i - 1]
        base = i * stride
        base_prev = (i - 1) * stride
        for k in range(1, ns + 1):
            d = di[k - 1]
            c_diag = cost_flat[base_prev + k - 1]
            c_up = cost_flat[base_prev + k]
            c_left = cost_flat[base + k - 1]
            m = c_diag
            if c_up < m: m = c_up
            if c_left < m: m = c_left
            cost_flat[base + k] = d + m
    
    # Backtrack
    path = []
    i, k = nj, ns
    while i > 0 or k > 0:
        if i > 0 and k > 0:
            path.append((i - 1, k - 1))
        elif i > 0:
            path.append((i - 1, max(0, k - 1)))
        else:
            break
        choices = []
        if i > 0 and k > 0:
            choices.append((cost[i - 1, k - 1], i - 1, k - 1))
        if i > 0:
            choices.append((cost[i - 1, k], i - 1, k))
        if k > 0:
            choices.append((cost[i, k - 1], i, k - 1))
        _, ni, nk = min(choices)
        if ni == i and nk == k:
            break
        i, k = ni, nk
    path.reverse()
    return np.array(path)

def blend(j_audio, s_audio, ratio=0.5):
    """
    Blend spectral Jessica + SIWIS.
    ratio: 0.0 = Jessica pure, 1.0 = SIWIS pure
    """
    j = j_audio.astype(np.float64)
    s = s_audio.astype(np.float64)
    nj = max(1, len(j) // SEG_LEN)
    ns = max(1, len(s) // SEG_LEN)
    
    # Features + DTW
    fj = _mel_features(j)
    fs = _mel_features(s)
    path = _dtw_cosine(fj, fs)
    
    # Warp continu
    j_anchors = (path[:, 0] + 0.5) * SEG_LEN
    s_anchors = (path[:, 1] + 0.5) * SEG_LEN
    n_out = nj * SEG_LEN
    s_positions = np.clip(np.interp(np.arange(n_out, dtype=np.float64), j_anchors, s_anchors), 0, len(s) - 1)
    s_idx = s_positions.astype(np.int64)
    s_frac = s_positions - s_idx
    s_idx_next = np.minimum(s_idx + 1, len(s) - 1)
    s_warped = s[s_idx] * (1.0 - s_frac) + s[s_idx_next] * s_frac
    
    # Blend spectral
    j_trimmed = j[:n_out]
    n_frames = (n_out - N_FFT) // HOP + 1
    
    if n_frames < 1:
        out = j_trimmed * (1.0 - ratio) + s_warped * ratio
    else:
        starts = np.arange(n_frames) * HOP
        idx = starts[:, None] + np.arange(N_FFT)[None, :]
        J = np.fft.rfft(j_trimmed[idx] * WIN[None, :], axis=1).T
        S = np.fft.rfft(s_warped[idx] * WIN[None, :], axis=1).T
        
        mag_j = np.abs(J)
        mag_s = np.abs(S)
        phase_j = np.angle(J)
        n_bins = N_FFT // 2 + 1
        
        # Gate silence
        j_segs = j[:nj * SEG_LEN].reshape(nj, SEG_LEN)
        env_j = np.sqrt(np.mean(j_segs ** 2, axis=1))
        env_j_peak = np.max(env_j) if nj > 0 else 1.0
        gate_thresh = env_j_peak * 0.12
        gate_seg = np.where(env_j > gate_thresh, 1.0, (env_j / gate_thresh) ** 2)
        gate_centers = (np.arange(nj) + 0.5) * SEG_LEN
        frame_centers = np.arange(n_frames, dtype=np.float64) * HOP + N_FFT // 2
        gate_frames = np.clip(np.interp(frame_centers, gate_centers, gate_seg), 0.0, 1.0)
        
        # HF preserve
        freq_bins = np.arange(n_bins) * SR / N_FFT
        hf_mask = np.ones(n_bins)
        hf_zone = (freq_bins > 4000) & (freq_bins <= 8000)
        hf_mask[hf_zone] = 1.0 - 0.7 * (freq_bins[hf_zone] - 4000) / 4000
        hf_mask[freq_bins > 8000] = 0.3
        
        # Transient detect
        energy = np.sum(mag_j ** 2, axis=0)
        energy_diff = np.abs(np.diff(energy, prepend=energy[0]))
        energy_median = np.median(energy) + 1e-10
        transient = np.where(energy_diff / energy_median > 0.5, 0.3, 1.0)
        if smooth1d is not None:
            transient = smooth1d(transient, size=3)
        
        # Blend
        eff_ratio = ratio * gate_frames[None, :] * hf_mask[:, None] * transient[None, :]
        mag_blend = mag_j * (1.0 - eff_ratio) + mag_s * eff_ratio
        
        # Conservation d'énergie
        energy_j = np.sum(mag_j ** 2, axis=0)
        energy_b = np.sum(mag_blend ** 2, axis=0)
        gain = np.where(energy_b > 0, np.sqrt(energy_j / energy_b), 1.0)
        mag_blend *= gain[None, :]
        
        # iSTFT overlap-add vectorisée
        blend_frames = np.fft.irfft(mag_blend * np.exp(1j * phase_j), axis=0).T
        blend_frames *= WIN[None, :]
        out = np.zeros(n_out, dtype=np.float64)
        win_sum = np.zeros(n_out, dtype=np.float64)
        frame_idx = np.arange(n_frames)[:, None]
        sample_idx = np.arange(N_FFT)[None, :]
        target_idx = (frame_idx * HOP + sample_idx).ravel()
        np.add.at(out, target_idx, blend_frames.ravel())
        np.add.at(win_sum, target_idx, np.tile(WIN_SQ, n_frames))
        stable = win_sum > 0.1
        out[stable] /= win_sum[stable]
        out[~stable] = j_trimmed[~stable]
    
    # Normalisation
    peak = np.max(np.abs(out))
    if peak > 0:
        out *= 31000.0 / peak
    return out.astype(np.float32)

def synth_both(piper_voice, piper_voice2, text):
    """Synthèse séquentielle Jessica + SIWIS + blend (CUDA safe)."""
    try:
        j_audio = np.concatenate([c.audio_int16_array for c in piper_voice.synthesize(text)])
    except Exception:
        return None
    try:
        s_audio = np.concatenate([c.audio_int16_array for c in piper_voice2.synthesize(text)])
    except Exception:
        return j_audio.astype(np.float32)
    return blend(j_audio, s_audio, 0.5)
