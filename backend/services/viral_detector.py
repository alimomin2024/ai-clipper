"""Transcript-based, deterministic clip ranking with no network or paid service."""

import re
import logging
import subprocess
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


HOOK_RE = re.compile(
    r"\b(why|how|what if|here's|here is|the truth|the problem|the secret|"
    r"the reason|most people|nobody|never|stop|mistake|imagine|turns out)\b",
    re.IGNORECASE,
)
QUESTION_RE = re.compile(r"\?|\b(why|how|what|when|where|who)\b", re.IGNORECASE)
NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?%?\b")
WORD_RE = re.compile(r"[\w']+", re.UNICODE)


class ViralMomentDetector:
    """Find distinct 20–60 second speech windows and rank local textual signals.

    Scores are ranking hints from transcript features, not a prediction that a clip
    will go viral. The algorithm deliberately makes no external model calls.
    """

    def __init__(self, api_key: Optional[str] = None):
        # Keep the argument for callers from older releases. It is intentionally unused.
        self.api_key = None

    def detect_clips(
        self,
        transcript_data: Dict[str, Any],
        video_title: str,
        video_duration: float,
        min_duration: int = 20,
        max_duration: int = 60,
        target_clips: int = 4,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        video_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if progress_callback:
            progress_callback(55.0, "Ranking transcript moments with local signals…")

        segments = []
        for segment in transcript_data.get("segments", []):
            try:
                start = max(0.0, float(segment["start"]))
                end = min(float(video_duration), float(segment["end"]))
                text = str(segment.get("text") or "").strip()
            except (KeyError, TypeError, ValueError):
                continue
            if end > start and text:
                segments.append({"start": start, "end": end, "text": text})
        segments.sort(key=lambda row: row["start"])
        min_duration = max(10, int(min_duration))
        max_duration = max(min_duration, min(60, int(max_duration)))
        candidates = []
        for start_index, first in enumerate(segments):
            # Prefer starting on a transcript sentence boundary.
            if start_index and not segments[start_index - 1]["text"].rstrip().endswith((".", "?", "!")):
                continue
            start = first["start"]
            endings = []
            for end_index in range(start_index, len(segments)):
                end = segments[end_index]["end"]
                duration = end - start
                if duration > max_duration:
                    break
                if duration >= min_duration and segments[end_index]["text"].rstrip().endswith((".", "?", "!")):
                    endings.append((abs(duration - 36.0), end_index, end))
            # If punctuation is missing in ASR output, retain one conservative
            # fallback boundary within the platform length range.
            if not endings:
                possible = [
                    (abs((segments[index]["end"] - start) - 36.0), index, segments[index]["end"])
                    for index in range(start_index, len(segments))
                    if min_duration <= segments[index]["end"] - start <= max_duration
                ]
                endings = sorted(possible)[:1]
            for _, end_index, end in endings:
                if abs((end - start) - 36.0) > 12.0:
                    continue
                text = " ".join(row["text"] for row in segments[start_index : end_index + 1]).strip()
                tokens = WORD_RE.findall(text)
                if len(tokens) < 12:
                    continue
                candidates.append(self._make_candidate(text, tokens, start, end, video_title))

        # Keep high scoring windows while limiting repeated content.
        selected = []
        for candidate in sorted(candidates, key=lambda item: item["virality_score"], reverse=True):
            if any(self._overlap_ratio(candidate, chosen) >= 0.45 for chosen in selected):
                continue
            selected.append(candidate)
            if len(selected) >= max(1, min(int(target_clips), 10)):
                break
        if selected:
            return selected
        if not video_path:
            return []
        if progress_callback:
            progress_callback(58.0, "No speech moments found; ranking visual scenes locally…")
        return self._detect_visual_clips(
            video_path=video_path,
            video_title=video_title,
            video_duration=float(video_duration),
            min_duration=min_duration,
            max_duration=max_duration,
            target_clips=target_clips,
        )

    @staticmethod
    def _detect_visual_clips(
        video_path: str,
        video_title: str,
        video_duration: float,
        min_duration: int,
        max_duration: int,
        target_clips: int,
    ) -> List[Dict[str, Any]]:
        """Choose variable-length windows whose cuts align with detected shot changes."""
        if video_duration < 20:
            return []
        actual_duration = float(video_duration)
        cut_times = ViralMomentDetector._detect_scene_cuts(video_path, actual_duration)
        points = [0.0]
        for cut in cut_times:
            if cut - points[-1] >= 1.0 and actual_duration - cut >= 1.0:
                points.append(cut)
        points.append(actual_duration)

        requested = max(1, min(int(target_clips), 10))
        possible_count = max(1, min(requested, int(actual_duration // min_duration)))
        ranges: List[tuple[float, float, bool, bool]] = []
        if actual_duration <= requested * max_duration:
            # When the source can fit into the requested set, divide it into
            # variable-length, scene-aligned clips instead of fixed 35s slices.
            count = possible_count
            ideal = actual_duration / count
            ranges = ViralMomentDetector._partition_on_cuts(points, count, ideal, min_duration, max_duration)
            if not ranges:
                ranges = ViralMomentDetector._uniform_ranges(actual_duration, count, min_duration, max_duration)
        else:
            # For very long sources, take one scene-aligned window from each
            # time band so the set covers the whole recording.
            band_size = actual_duration / possible_count
            for band in range(possible_count):
                band_start = band * band_size
                band_end = (band + 1) * band_size
                center = (band_start + band_end) / 2.0
                options = []
                for start in points[:-1]:
                    if start < band_start - max_duration / 2 or start > band_end:
                        continue
                    for end in points:
                        length = end - start
                        midpoint = (start + end) / 2.0
                        if min_duration <= length <= max_duration and band_start <= midpoint <= band_end:
                            cost = abs(length - 36.0) + abs(midpoint - center) * 0.25
                            options.append((cost, start, end))
                if options:
                    _, start, end = min(options)
                    ranges.append((start, end, False, False))
                else:
                    start = max(band_start, center - 18.0)
                    end = min(band_end, center + 18.0)
                    ranges.append((start, end, band > 0, band < possible_count - 1))

        results = []
        for index, (start, end, fade_in, fade_out) in enumerate(ranges, start=1):
            length = end - start
            if length < min_duration or length > max_duration:
                continue
            inside_cuts = sum(start < cut < end for cut in cut_times)
            score = max(50, min(82, 58 + min(inside_cuts, 12) * 2))
            results.append({
                "title": f"Visual moment {index}",
                "hook": "Visual highlight from the source video.",
                "start_time": round(start, 2),
                "end_time": round(end, 2),
                "duration": round(length, 2),
                "virality_score": score,
                "virality_reason": "Scene-aware visual edit; clip boundaries align to shot changes." if not (fade_in or fade_out) else "Visual edit with a short fade at a boundary where no clean shot transition was found.",
                "social_caption": f"A visual moment from {video_title}. #shorts #reels",
                "key_quote": "",
                "moment_type": "visual",
                "fade_in": fade_in,
                "fade_out": fade_out,
            })
        return results

    @staticmethod
    def _detect_scene_cuts(video_path: str, duration: float) -> List[float]:
        command = [
            "ffmpeg", "-hide_banner", "-i", video_path,
            "-vf", "scale=320:-2,select='gt(scene,0.3)',showinfo",
            "-an", "-fps_mode", "vfr", "-f", "null", "-",
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=max(60, int(duration * 1.5)))
        except (OSError, subprocess.TimeoutExpired) as error:
            logger.warning("Scene detection unavailable; using clean fallback boundaries: %s", error)
            return []
        if result.returncode != 0:
            logger.warning("Scene detection failed; using clean fallback boundaries: %s", result.stderr[-500:])
            return []
        raw = [float(value) for value in re.findall(r"pts_time:([0-9.]+)", result.stderr)]
        # FFmpeg may report neighboring frames around one edit. Collapse these
        # into one cut point and avoid cuts near the very start or end.
        clustered = []
        for value in raw:
            if value < 0.5 or value > duration - 0.5:
                continue
            if clustered and value - clustered[-1] < 0.75:
                clustered[-1] = (clustered[-1] + value) / 2.0
            else:
                clustered.append(value)
        return clustered

    @staticmethod
    def _partition_on_cuts(points: List[float], count: int, ideal: float, min_duration: int, max_duration: int):
        """Find a full-source partition using shot cuts and lengths near the ideal."""
        last = len(points) - 1
        infinity = float("inf")
        cost = [[infinity] * (last + 1) for _ in range(count + 1)]
        previous = [[None] * (last + 1) for _ in range(count + 1)]
        cost[0][0] = 0.0
        for clips in range(1, count + 1):
            for end_index in range(1, last + 1):
                for start_index in range(end_index):
                    length = points[end_index] - points[start_index]
                    if not min_duration <= length <= max_duration:
                        continue
                    candidate = cost[clips - 1][start_index] + (length - ideal) ** 2
                    if candidate < cost[clips][end_index]:
                        cost[clips][end_index] = candidate
                        previous[clips][end_index] = start_index
        if cost[count][last] == infinity:
            return []
        indices = [last]
        end_index = last
        for clips in range(count, 0, -1):
            end_index = previous[clips][end_index]
            if end_index is None:
                return []
            indices.append(end_index)
        indices.reverse()
        return [(points[a], points[b], False, False) for a, b in zip(indices, indices[1:])]

    @staticmethod
    def _uniform_ranges(duration: float, count: int, min_duration: int, max_duration: int):
        ideal = duration / count
        if not min_duration <= ideal <= max_duration:
            return []
        boundaries = [duration * i / count for i in range(count + 1)]
        return [
            (boundaries[i], boundaries[i + 1], i > 0, i < count - 1)
            for i in range(count)
        ]

        results = []
        for index, item in enumerate(sorted(selected, key=lambda row: row["start"]), start=1):
            title = f"Visual moment {index}"
            caption = f"A visual moment from {video_title}. #shorts #reels"
            results.append({
                "title": title,
                "hook": "Visual highlight from the source video.",
                "start_time": round(item["start"], 2),
                "end_time": round(item["end"], 2),
                "duration": round(item["end"] - item["start"], 2),
                "virality_score": item["score"],
                "virality_reason": "Local visual signals: scene changes and motion; no distinct spoken moment was available.",
                "social_caption": caption,
                "key_quote": "",
                "moment_type": "visual",
            })
        return results

    @staticmethod
    def _overlap_ratio(left: Dict[str, Any], right: Dict[str, Any]) -> float:
        intersection = max(0.0, min(left["end_time"], right["end_time"]) - max(left["start_time"], right["start_time"]))
        shortest = min(left["duration"], right["duration"])
        return intersection / shortest if shortest > 0 else 0.0

    @staticmethod
    def _make_candidate(text: str, tokens: List[str], start: float, end: float, title: str) -> Dict[str, Any]:
        duration = end - start
        lower = text.lower()
        opening = text[:180]
        hook = bool(HOOK_RE.search(opening))
        has_question = bool(QUESTION_RE.search(opening))
        has_number = bool(NUMBER_RE.search(text))
        sentence_marks = text.count("?") + text.count("!")
        complete = text.rstrip().endswith((".", "!", "?", '"'))
        rate = len(tokens) / max(duration, 1.0)
        pace = max(0.0, 12.0 - abs(rate - 2.6) * 5.0)
        score = 58 + (16 if hook else 0) + (8 if has_question else 0) + (6 if has_number else 0)
        score += min(7, sentence_marks * 2) + pace + (3 if complete else 0)
        score = max(55, min(98, round(score)))

        first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
        if len(first_sentence) < 12:
            first_sentence = text[:120].strip()
        title_seed = re.sub(r"\s+", " ", first_sentence).strip(" .?!")
        clip_title = title_seed[:42].rstrip(" ,:;-") or title[:42] or "Video highlight"
        signals = []
        if hook:
            signals.append("curiosity-led opening")
        if has_question:
            signals.append("question hook")
        if has_number:
            signals.append("concrete number")
        if rate >= 1.8:
            signals.append("steady speech pace")
        if complete:
            signals.append("complete sentence ending")
        reason = "Local transcript signals: " + (", ".join(signals) or "coherent speech and pacing")

        topical = []
        for word in tokens:
            clean = re.sub(r"[^a-z0-9]", "", word.lower())
            if len(clean) >= 5 and clean not in {"there", "their", "which", "about", "would", "could", "should", "because", "people", "really"} and clean not in topical:
                topical.append(clean)
            if len(topical) == 2:
                break
        tags = " ".join(f"#{word}" for word in topical)
        caption = f"{title_seed[:180]} #shorts #reels {tags}".strip()
        return {
            "title": clip_title,
            "hook": first_sentence[:240],
            "start_time": round(start, 2),
            "end_time": round(end, 2),
            "duration": round(duration, 2),
            "virality_score": score,
            "virality_reason": reason,
            "social_caption": caption,
            "key_quote": first_sentence[:300],
        }
