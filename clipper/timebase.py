"""Exact editor endpoints and half-open intervals [start, end).

Video boundaries use integer frames. Audio and subtitle times keep their
microsecond precision; they are not rounded to video frames.
"""
from fractions import Fraction

MICROSECONDS = 1_000_000


def frame_rate(value):
    if isinstance(value, dict):
        rate = Fraction(value['numerator'], value['denominator'])
    else:
        rate = Fraction(str(value))
    if rate <= 0:
        raise ValueError('FPS harus lebih dari nol')
    return rate


def seconds_to_us(seconds):
    return round(Fraction(str(seconds)) * MICROSECONDS)


def seconds_to_frame(seconds, fps):
    return round(Fraction(str(seconds)) * frame_rate(fps))


def frame_to_us(frame, fps):
    if type(frame) is not int or frame < 0:
        raise ValueError('Batas frame harus bilangan bulat nonnegatif')
    return round(Fraction(frame * MICROSECONDS, 1) / frame_rate(fps))


def endpoint_range(start, end):
    """Convert each endpoint once; never round a start and duration separately."""
    a, b = seconds_to_us(start), seconds_to_us(end)
    if a < 0 or b <= a:
        raise ValueError('Rentang waktu harus positif dan tidak terbalik')
    return a, b - a


def video_range(shot, fps):
    a = shot.get('start_frame', seconds_to_frame(shot['start'], fps))
    b = a + shot['duration_frames'] if 'duration_frames' in shot else seconds_to_frame(shot['end'], fps)
    if a != seconds_to_frame(shot['start'], fps) or b != seconds_to_frame(shot['end'], fps):
        raise ValueError('Batas frame shot berbeda dari waktu pada rencana')
    start, end = frame_to_us(a, fps), frame_to_us(b, fps)
    if end <= start:
        raise ValueError('Shot harus memuat setidaknya satu frame')
    return start, end - start


def interval_issues(intervals, *, duration, contiguous=False):
    """Check one track only. Different video/text tracks may overlap by design."""
    issues = []
    previous = 0
    for i, pair in enumerate(intervals):
        if len(pair) != 2 or any(type(n) is not int for n in pair):
            issues.append(f'Segmen {i+1}: batas waktu harus bilangan bulat')
            continue
        start, end = pair
        if start < 0 or end <= start or end > duration:
            issues.append(f'Segmen {i+1}: rentang di luar timeline atau durasi tidak positif')
        if start < previous:
            issues.append(f'Segmen {i+1}: tumpang tindih {previous-start} unit waktu')
        elif contiguous and start != previous:
            issues.append(f'Segmen {i+1}: celah {start-previous} unit waktu')
        previous = max(previous, end)
    if contiguous and previous != duration:
        issues.append(f'Akhir track {previous} tidak sama dengan durasi timeline {duration}')
    return issues


def video_track_ranges(plan):
    ranges = [video_range(shot, plan['fps']) for shot in plan['shots']]
    duration_frames = plan.get('duration_frames', seconds_to_frame(plan['duration'], plan['fps']))
    duration = frame_to_us(duration_frames, plan['fps'])
    if duration_frames != seconds_to_frame(plan['duration'], plan['fps']):
        raise ValueError('Durasi frame berbeda dari waktu timeline')
    issues = interval_issues([(a, a+d) for a, d in ranges], duration=duration, contiguous=True)
    if issues:
        raise ValueError('Track video tidak valid: ' + '; '.join(issues))
    return ranges, duration
