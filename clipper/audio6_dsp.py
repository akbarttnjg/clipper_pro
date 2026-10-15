"""Bounded local DSP. No downloads, source rewriting, or inferred transcripts."""
from pathlib import Path
import math
import subprocess
import numpy as np
from .audio6_contract import RATE,MAX_SECONDS

def decode(path,*,start=0.,seconds=None):
    if seconds is not None and not 0<seconds<=MAX_SECONDS:raise ValueError('Budget audio M6 maksimal 600 detik')
    args=['ffmpeg','-nostdin','-v','error']
    if start:args+=['-ss',str(start)]
    args+=['-i',str(path),'-vn']
    if seconds is not None:args+=['-t',str(seconds)]
    args+=['-ar',str(RATE),'-ac','2','-f','f32le','-']
    p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        data=p.stdout.read((MAX_SECONDS*RATE*2+1)*4)
        if len(data)>MAX_SECONDS*RATE*2*4:raise ValueError('Audio melebihi budget decode 600 detik')
        error=p.stderr.read();rc=p.wait(timeout=120)
        if rc:raise ValueError('Decode audio gagal: '+error.decode('utf-8','replace')[-800:])
    finally:
        if p.poll() is None:p.kill();p.wait()
        p.stdout.close();p.stderr.close()
    result=np.frombuffer(data,dtype='<f4').reshape(-1,2).copy()
    if not len(result) or not np.isfinite(result).all():raise ValueError('PCM kosong/tidak finite')
    return result

def write(path,samples):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    x=np.asarray(samples,dtype='<f4')
    if x.ndim!=2 or x.shape[1]!=2 or not np.isfinite(x).all():raise ValueError('PCM stereo tidak valid')
    pending=path.with_name(path.stem+'.pending.wav')
    try:
        p=subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','f32le','-ar',str(RATE),'-ac','2','-i','pipe:0','-c:a','pcm_f32le',str(pending)],input=x.tobytes(),capture_output=True,timeout=180)
        if p.returncode:raise ValueError('Simpan PCM gagal: '+p.stderr.decode('utf-8','replace')[-800:])
        pending.replace(path)
    finally:pending.unlink(missing_ok=True)
    return str(path.resolve())

def fixed(samples,count):
    out=np.zeros((count,2),dtype=np.float32);n=min(count,len(samples));out[:n]=samples[:n];return out

def loop(samples,count,crossfade_seconds):
    """Overlap only loop seams; output length stays sample-exact."""
    if count<=len(samples):return samples[:count].copy()
    overlap=min(round(crossfade_seconds*RATE),len(samples)//4)
    if len(samples)<2 or len(samples)-overlap<1:raise ValueError('Musik terlalu pendek untuk loop')
    out=np.zeros((count,2),np.float32);out[:min(count,len(samples))]=samples[:count]
    start=len(samples)-overlap
    while start<count:
        n=min(len(samples),count-start);piece=samples[:n]
        k=min(overlap,n)
        if k:
            ramp=np.linspace(0,1,k,endpoint=True,dtype=np.float32)[:,None]
            out[start:start+k]=out[start:start+k]*(1-ramp)+piece[:k]*ramp
        out[start+k:start+n]=piece[k:n];start+=len(samples)-overlap
    return out

def fade(samples,seconds_in,seconds_out):
    x=samples.copy();n=len(x)
    for count,side in ((min(n,round(seconds_in*RATE)),'in'),(min(n,round(seconds_out*RATE)),'out')):
        if count:
            ramp=np.sin(np.linspace(0,math.pi/2,count,dtype=np.float32))[:,None]
            if side=='in':x[:count]*=ramp
            else:x[-count:]*=ramp[::-1]
    return x

def duck_envelope(count,intervals,attenuation_db,attack_ms,release_ms):
    out=np.ones(count,np.float32);bottom=10**(attenuation_db/20)
    attack=round(attack_ms*RATE/1000);release=round(release_ms*RATE/1000)
    for a,b in intervals:
        left=max(0,min(count,round(a*RATE)));right=max(left,min(count,round(b*RATE)))
        if left==right:continue
        before=max(0,left-attack);after=min(count,right+release)
        if before<left:out[before:left]=np.minimum(out[before:left],np.linspace(1,bottom,left-before,endpoint=False))
        out[left:right]=np.minimum(out[left:right],bottom)
        if right<after:out[right:after]=np.minimum(out[right:after],np.linspace(bottom,1,after-right,endpoint=True))
    return out

def wpe(samples,strength=.35):
    """Delayed linear prediction (WPE), small batches and fixed sample clock.

    This is blind DSP dereverberation, not recovery of the original dry voice.
    Perceptual quality must be judged against the separately retained input.
    """
    if strength==0 or len(samples)<2048:return samples.copy()
    nfft=512;hop=128;delay=3;taps=4;window=np.sqrt(np.hanning(nfft).astype(np.float64))
    out=np.zeros_like(samples)
    # Independent ten-second windows bound matrices on a four-GB machine.
    block=10*RATE
    for origin in range(0,len(samples),block):
        original=samples[origin:origin+block];x=np.pad(original,((nfft,nfft),(0,0)),mode='reflect')
        count=math.ceil((len(x)-nfft)/hop)+1;needed=(count-1)*hop+nfft
        x=np.pad(x,((0,max(0,needed-len(x))),(0,0)))
        frames=np.lib.stride_tricks.sliding_window_view(x,nfft,axis=0)[::hop][:count]
        y=np.fft.rfft(frames*window,axis=-1).transpose(2,1,0);clean=y.copy()
        for f in range(0,len(y),32):
            observed=y[f:f+32];T=observed.shape[-1];valid=T-delay-taps+1
            if valid<=taps*2:continue
            delayed=np.concatenate([observed[:,:,taps-1-k: taps-1-k+valid] for k in range(taps)],axis=1)
            target=observed[:,:,delay+taps-1:];current=target.copy()
            for _ in range(3):
                power=np.maximum(np.mean(abs(current)**2,axis=1),np.mean(abs(current)**2,axis=(1,2))[:,None]*1e-6+1e-10)
                weighted=delayed/power[:,None,:]
                R=np.einsum('fkt,flt->fkl',weighted,delayed.conj())
                P=np.einsum('fkt,fct->fkc',weighted,target.conj())
                diagonal=np.maximum(np.trace(R,axis1=1,axis2=2).real/R.shape[1]*1e-6,1e-8)
                R+=diagonal[:,None,None]*np.eye(R.shape[1])[None]
                G=np.linalg.solve(R,P)
                prediction=np.einsum('fkc,fkt->fct',G.conj(),delayed)
                current=target-prediction
            clean[f:f+32,:,delay+taps-1:]=target*(1-strength)+current*strength
        restored=np.fft.irfft(clean.transpose(2,1,0),n=nfft,axis=-1)*window
        merged=np.zeros((needed,2));weights=np.zeros(needed)
        for i,frame in enumerate(restored):merged[i*hop:i*hop+nfft]+=frame.T;weights[i*hop:i*hop+nfft]+=window**2
        merged/=np.maximum(weights[:,None],1e-10)
        processed=merged[nfft:nfft+len(original)]
        # Blend block borders against the input, preventing discontinuities.
        ramp=min(nfft,len(processed)//2)
        if ramp:
            alpha=np.ones(len(processed));alpha[:ramp]=np.linspace(0,1,ramp);alpha[-ramp:]=np.linspace(1,0,ramp)
            processed=original*(1-alpha[:,None])+processed*alpha[:,None]
        out[origin:origin+len(original)]=processed
    if not np.isfinite(out).all():raise ValueError('WPE menghasilkan PCM tidak finite; sumber tetap tersedia')
    return out
