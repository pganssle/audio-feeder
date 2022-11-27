import typing

import attrs


class _Floatable(typing.Protocol):
    def __float__(self) -> float:  # pragma: nocover
        ...


Scorable = typing.TypeVar("Scorable", bound=_Floatable)


@attrs.frozen(order=True)
class _MemoEntry:
    score: float
    previous_split: typing.Optional[int] = None


CostFunc = typing.Callable[[typing.Iterable[_Floatable]], float]


def asymmetric_cost(
    target: float, pos_exponent: float = 1.25, neg_exponent: float = 1.75
) -> CostFunc:
    """Generates a cost function targeting `target`.

    This is an exponential cost function asymmetric about `target`.
    `pos_exponent` is applied to deviations greater than `target` and
    `neg_exponent` to deviations lower than `target`.

    `target` is assumed to be duration in seconds.
    """

    def segment_cost(values: typing.Iterable[_Floatable]) -> float:
        s = sum(map(float, values)) - target
        if s < 0:
            return abs(s) ** neg_exponent
        else:
            return s**pos_exponent

    return segment_cost


def segment(
    values: typing.Sequence[Scorable], cost_func: CostFunc = asymmetric_cost(3600)
) -> typing.Sequence[typing.Sequence[Scorable]]:
    """Breaks up `values` into subsets in such a way to minimize the cost function."""

    # This uses a dynamic programming approach suggested by Nathaniel Smith
    #
    # The idea works like this: iterate from left to right assuming you are
    # going to break up the list immediately to the right of the pointer as you
    # go, then you recursively calculate the total score of breaking up the list
    # at each point to the left of your pointer (caching the calculation in a
    # memo table to avoid recalculating).
    memo_table: typing.MutableSequence[typing.Optional[_MemoEntry]] = [None] * (
        len(values) + 1
    )

    # Initialize the list with a zero score — this represents an empty segment.
    memo_table[0] = _MemoEntry(score=0.0, previous_split=None)
    for i in range(1, len(values) + 1):
        candidates = []
        for j in range(i):
            # We already know the score for the optimal breakpoint at each point
            # up to i under the assumption that the length of the list is length
            # i. Now we say, "What is the total score assuming I break up the
            # values[0:j] portion of the list optimally (as calculated in
            # previous iterations), and put the rest of `j` all together in one
            # group.
            new_score = cost_func(values[j:i])
            memoized_score = memo_table[j].score  # type: ignore[union-attr]
            candidates.append(
                _MemoEntry(score=new_score + memoized_score, previous_split=j)
            )

        # Now that we have all potential split positions, we choose the one with
        # the minimum score to go into the memo table.
        memo_table[i] = min(candidates)

    # The memo table is now fully populated, so we have the optimal "previous
    # split" at each position in the table, including the beginning (which is
    # always an empty list) and the point 1 after the length of `values`. We
    # start at the end of the list and work backwards.
    breaks = []
    current_break: int = len(values)
    while True:
        breaks.append(current_break)
        if (next_split := memo_table[current_break].previous_split) is None:  # type: ignore[union-attr]
            break
        current_break = next_split

    # Now we have a list of places to break up the input sequence, and we want
    # to translate that into actual subsequences, so for example:
    # values = [60, 1, 59], breaks = [3, 1, 0] → [[60], [1, 59]]
    breaks.reverse()
    out_sequence = []
    for start, end in zip(breaks[:-1], breaks[1:]):
        out_sequence.append(values[start:end])

    return out_sequence
