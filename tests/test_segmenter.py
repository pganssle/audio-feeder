import functools
import itertools
import typing
from datetime import timedelta

import hypothesis
import pytest

from audio_feeder import segmenter

Minimizer = typing.Callable[
    [typing.Sequence[segmenter.Scorable], segmenter.CostFunc],
    typing.Tuple[typing.Sequence[typing.Sequence[segmenter.Scorable]], float],
]

_T = typing.TypeVar("_T")


def all_segmentations(
    arr: typing.Sequence[_T],
) -> typing.Iterable[typing.Iterable[typing.Sequence[_T]]]:
    yield (arr,)

    for i in range(1, len(arr)):
        for subseg in all_segmentations(arr[i:]):
            yield itertools.chain((arr[:i],), subseg)


@functools.lru_cache
def make_segmentation_scorer(
    cost_func: segmenter.CostFunc,
) -> typing.Callable[[typing.Iterable[typing.Sequence[float]]], float]:
    def segmentation_scorer(segments: typing.Iterable[typing.Sequence[float]]) -> float:
        return sum(map(cost_func, segments))

    return segmentation_scorer


def brute_force_minimization(
    arr: typing.Sequence[segmenter.Scorable],
    cost_func: segmenter.CostFunc = segmenter.asymmetric_cost(3600),
) -> typing.Tuple[typing.Sequence[typing.Sequence[segmenter.Scorable]], float]:
    segmentation_scorer = make_segmentation_scorer(cost_func)

    best_segmentation = min(map(list, all_segmentations(arr)), key=segmentation_scorer)

    return best_segmentation, segmentation_scorer(best_segmentation)


def segment_with_score(
    arr: typing.Sequence[segmenter.Scorable], cost_func: segmenter.CostFunc
) -> typing.Tuple[typing.Sequence[typing.Sequence[segmenter.Scorable]], float]:

    sequence = segmenter.segment(arr, cost_func)
    scorer = make_segmentation_scorer(cost_func)
    return sequence, scorer(sequence)


@pytest.mark.parametrize("algo", [brute_force_minimization, segment_with_score])
@pytest.mark.parametrize(
    "input,optimal",
    [
        ((60, 1, 1, 1, 59), (61, 61)),
        ((15, 15, 20, 45, 25), (50, 70)),
        ((60, 45, 45, 35, 35, 10, 15), (60, 90, 95)),
        ((60, 45, 45, 35, 35, 10, 50), (60, 90, 70, 60)),
        ((60, 60, 60, 1, 61), (60, 60, 61, 61)),
        ((60, 1, 61, 1, 60), (61, 61, 61)),
    ],
)
def test_algo(
    subtests,
    algo: Minimizer,
    input: typing.Sequence[int],
    optimal: typing.Sequence[int],
):
    cost_func = segmenter.asymmetric_cost(60)
    actual_segments, score = algo(input, cost_func)
    actual = list(map(sum, actual_segments))
    optimal_score = make_segmentation_scorer(cost_func)([(v,) for v in optimal])

    with subtests.test("Result"):
        assert tuple(actual) == tuple(optimal)

    with subtests.test("Score"):
        assert score == pytest.approx(optimal_score)


@hypothesis.settings(deadline=timedelta(seconds=30))
@hypothesis.given(
    chapters=hypothesis.strategies.lists(
        hypothesis.strategies.floats(
            allow_nan=False, min_value=0.1, max_value=500.0 * 3600.0
        ),
        min_size=1,
        max_size=12,
    )
)
def test_algo_comparison(chapters: typing.Sequence[int]) -> None:
    cost_func = segmenter.asymmetric_cost(3600.0)
    _bf_results, bf_score = brute_force_minimization(chapters, cost_func=cost_func)
    _dp_results, dp_score = segment_with_score(chapters, cost_func=cost_func)

    # We only assert that the scores are the same, because there are some
    # cases where more than one solution minimizes the score, e.g.
    # [[60, 1], [60]] and [[60], [1, 60]] have identical scores.
    assert bf_score == pytest.approx(dp_score)
