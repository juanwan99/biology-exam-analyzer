import asyncio

from analysis_scheduling import gather_longest_first


def test_longest_question_starts_first_and_order_is_kept():
    questions = [
        {"id": 1, "content": "短选择题"},
        {"id": 2, "content": "大题" * 400},
        {"id": 3, "content": "带图题", "_media_for_ai": [{"type": "image"}]},
    ]
    started = []

    async def run(q):
        started.append(q["id"])
        await asyncio.sleep(0)
        return q["id"] * 10

    async def main():
        sem = asyncio.Semaphore(1)

        async def limited(q):
            async with sem:
                return await run(q)

        return await gather_longest_first(questions, limited)

    assert asyncio.run(main()) == [10, 20, 30]
    assert started == [2, 3, 1]
