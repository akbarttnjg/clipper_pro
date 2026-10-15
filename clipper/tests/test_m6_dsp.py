import numpy as np
from ..audio6_contract import RATE
from ..audio6_dsp import loop,fade,duck_envelope,wpe,write,decode

def test_loop_crossfade_removes_discontinuous_seam_and_keeps_sample_count():
    source=np.repeat(np.linspace(.4,-.4,4800,dtype=np.float32)[:,None],2,axis=1)
    smooth=loop(source,48000,.02);hard=loop(source,48000,0)
    assert smooth.shape==(48000,2)
    assert np.max(abs(np.diff(smooth[:,0])))<np.max(abs(np.diff(hard[:,0])))/10

def test_fade_does_not_shift_content_and_has_exact_endpoints():
    original=np.ones((48000,2),np.float32);out=fade(original,.1,.1)
    assert out[0,0]==0 and out[-1,0]==0 and np.allclose(out[4800:43200],1)
    assert np.array_equal(original,np.ones_like(original))

def test_ducking_covers_quiet_critical_words_with_attack_release_and_true_off_identity():
    envelope=duck_envelope(RATE*2,[[.5,.8]],-20,100,200)
    assert np.allclose(envelope[round(.5*RATE):round(.8*RATE)],.1)
    assert .1<envelope[round(.45*RATE)]<1 and .1<envelope[round(.9*RATE)]<1
    assert envelope[0]==envelope[-1]==1
    assert np.array_equal(duck_envelope(RATE,[], -20,100,200),np.ones(RATE))

def test_overlapping_duck_intervals_never_raise_gain_between_words():
    a=duck_envelope(RATE,[[.2,.5],[.4,.7]],-14,80,350)
    assert np.max(a[round(.2*RATE):round(.7*RATE)])<=10**(-14/20)+1e-6

def test_float_PCM_roundtrip_retains_samples_and_does_not_clip_before_limiter(tmp_path):
    x=np.repeat(np.linspace(-1.2,1.2,9600,dtype=np.float32)[:,None],2,axis=1)
    target=write(tmp_path/'float.wav',x);actual=decode(target,seconds=.2)
    assert np.array_equal(actual,x) and float(actual.max())>1

def test_WPE_zero_strength_is_identity_and_processing_preserves_finite_clock():
    rng=np.random.default_rng(42);x=rng.normal(0,.03,(12000,2)).astype(np.float32)
    assert np.array_equal(wpe(x,0),x)
    result=wpe(x,.3);assert result.shape==x.shape and np.isfinite(result).all()
    assert not np.array_equal(result,x)

def test_WPE_does_not_generate_audio_from_digital_silence():
    x=np.zeros((8000,2),np.float32);assert np.allclose(wpe(x,.5),0)
