"""Tests for workflow execution strategies."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from emdx.workflows.base import ExecutionMode, StageConfig, StageResult
from emdx.workflows.strategies import get_strategy
from emdx.workflows.strategies.base import make_title, ExecutionStrategy
from emdx.workflows.strategies.single import SingleStrategy
from emdx.workflows.strategies.parallel import ParallelStrategy
from emdx.workflows.strategies.iterative import IterativeStrategy
from emdx.workflows.strategies.adversarial import AdversarialStrategy
from emdx.workflows.strategies.dynamic import DynamicStrategy


class TestGetStrategy:
    """Test strategy dispatch."""

    def test_all_modes_have_strategies(self):
        for mode in ExecutionMode:
            strategy = get_strategy(mode)
            assert isinstance(strategy, ExecutionStrategy)

    def test_single_returns_single_strategy(self):
        assert isinstance(get_strategy(ExecutionMode.SINGLE), SingleStrategy)

    def test_parallel_returns_parallel_strategy(self):
        assert isinstance(get_strategy(ExecutionMode.PARALLEL), ParallelStrategy)

    def test_iterative_returns_iterative_strategy(self):
        assert isinstance(get_strategy(ExecutionMode.ITERATIVE), IterativeStrategy)

    def test_adversarial_returns_adversarial_strategy(self):
        assert isinstance(get_strategy(ExecutionMode.ADVERSARIAL), AdversarialStrategy)

    def test_dynamic_returns_dynamic_strategy(self):
        assert isinstance(get_strategy(ExecutionMode.DYNAMIC), DynamicStrategy)

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown execution mode"):
            get_strategy("nonexistent")


class TestMakeTitle:
    """Test the shared title-building helper."""

    def test_generic_fallback(self):
        stage = StageConfig(name="test", mode=ExecutionMode.SINGLE)
        assert make_title(stage, 0, 42) == "Workflow Agent Run #42"

    def test_task_titles_used(self):
        stage = StageConfig(name="test", mode=ExecutionMode.SINGLE)
        stage._task_titles = ["Fix auth bug", "Add tests"]
        assert make_title(stage, 0, 42) == "Delegate: Fix auth bug"
        assert make_title(stage, 1, 43) == "Delegate: Add tests"

    def test_task_title_truncated_at_60(self):
        stage = StageConfig(name="test", mode=ExecutionMode.SINGLE)
        stage._task_titles = ["x" * 100]
        title = make_title(stage, 0, 42)
        assert title == f"Delegate: {'x' * 60}"

    def test_item_label_takes_precedence(self):
        stage = StageConfig(name="test", mode=ExecutionMode.SINGLE)
        stage._task_titles = ["should not appear"]
        assert make_title(stage, 0, 42, item_label="feature/foo") == "Delegate: feature/foo"

    def test_index_out_of_range_falls_back(self):
        stage = StageConfig(name="test", mode=ExecutionMode.SINGLE)
        stage._task_titles = ["only one"]
        assert make_title(stage, 5, 42) == "Workflow Agent Run #42"


class TestSingleStrategy:
    """Test SingleStrategy execution."""

    @pytest.mark.asyncio
    async def test_single_success(self):
        strategy = SingleStrategy()
        stage = StageConfig(name="test", mode=ExecutionMode.SINGLE, prompt="Do something")

        with patch("emdx.workflows.strategies.single.wf_db") as mock_db, \
             patch("emdx.workflows.strategies.single.run_agent", new_callable=AsyncMock) as mock_agent, \
             patch("emdx.workflows.strategies.single.resolve_template", return_value="resolved prompt"):

            mock_db.create_individual_run.return_value = 1
            mock_agent.return_value = {
                'success': True,
                'output_doc_id': 100,
                'tokens_used': 500,
            }

            executor = MagicMock()
            result = await strategy.execute(
                stage_run_id=1, stage=stage, context={},
                stage_input=None, executor=executor,
            )

            assert result.success is True
            assert result.output_doc_id == 100
            assert result.tokens_used == 500
            mock_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_failure(self):
        strategy = SingleStrategy()
        stage = StageConfig(name="test", mode=ExecutionMode.SINGLE, prompt="Do something")

        with patch("emdx.workflows.strategies.single.wf_db") as mock_db, \
             patch("emdx.workflows.strategies.single.run_agent", new_callable=AsyncMock) as mock_agent, \
             patch("emdx.workflows.strategies.single.resolve_template", return_value="prompt"):

            mock_db.create_individual_run.return_value = 1
            mock_agent.return_value = {
                'success': False,
                'error_message': 'Agent crashed',
                'tokens_used': 0,
            }

            executor = MagicMock()
            result = await strategy.execute(
                stage_run_id=1, stage=stage, context={},
                stage_input=None, executor=executor,
            )

            assert result.success is False
            assert result.error_message == 'Agent crashed'


class TestIterativeStrategy:
    """Test IterativeStrategy execution."""

    @pytest.mark.asyncio
    async def test_iterative_chains_outputs(self):
        strategy = IterativeStrategy()
        stage = StageConfig(name="test", mode=ExecutionMode.ITERATIVE, prompt="Refine: {{prev}}", runs=2)

        call_count = 0

        async def mock_run_agent(**kwargs):
            nonlocal call_count
            call_count += 1
            return {
                'success': True,
                'output_doc_id': 100 + call_count,
                'tokens_used': 100,
            }

        mock_doc = {'content': f'output content', 'title': 'Output'}

        with patch("emdx.workflows.strategies.iterative.wf_db") as mock_db, \
             patch("emdx.workflows.strategies.iterative.run_agent", side_effect=mock_run_agent), \
             patch("emdx.workflows.strategies.iterative.resolve_template", side_effect=lambda t, c: t), \
             patch("emdx.workflows.strategies.iterative.document_service") as mock_docs:

            mock_db.create_individual_run.side_effect = [1, 2]
            mock_docs.get_document.return_value = mock_doc

            executor = MagicMock()
            result = await strategy.execute(
                stage_run_id=1, stage=stage, context={},
                stage_input="initial", executor=executor,
            )

            assert result.success is True
            assert call_count == 2
            assert len(result.individual_outputs) == 2
            assert result.tokens_used == 200

    @pytest.mark.asyncio
    async def test_iterative_stops_on_failure(self):
        strategy = IterativeStrategy()
        stage = StageConfig(name="test", mode=ExecutionMode.ITERATIVE, prompt="Do it", runs=3)

        async def fail_on_second(**kwargs):
            if kwargs.get('individual_run_id') == 2:
                return {'success': False, 'error_message': 'Failed', 'tokens_used': 0}
            return {'success': True, 'output_doc_id': 100, 'tokens_used': 50}

        with patch("emdx.workflows.strategies.iterative.wf_db") as mock_db, \
             patch("emdx.workflows.strategies.iterative.run_agent", side_effect=fail_on_second), \
             patch("emdx.workflows.strategies.iterative.resolve_template", side_effect=lambda t, c: t), \
             patch("emdx.workflows.strategies.iterative.document_service") as mock_docs:

            mock_db.create_individual_run.side_effect = [1, 2, 3]
            mock_docs.get_document.return_value = {'content': 'out', 'title': 'Out'}

            executor = MagicMock()
            result = await strategy.execute(
                stage_run_id=1, stage=stage, context={},
                stage_input=None, executor=executor,
            )

            assert result.success is False
            assert "Iteration 2 failed" in result.error_message


class TestAdversarialStrategy:
    """Test AdversarialStrategy execution."""

    @pytest.mark.asyncio
    async def test_adversarial_runs_three_phases(self):
        strategy = AdversarialStrategy()
        stage = StageConfig(name="test", mode=ExecutionMode.ADVERSARIAL, runs=3)

        run_count = 0

        async def mock_agent(**kwargs):
            nonlocal run_count
            run_count += 1
            return {'success': True, 'output_doc_id': 200 + run_count, 'tokens_used': 100}

        with patch("emdx.workflows.strategies.adversarial.wf_db") as mock_db, \
             patch("emdx.workflows.strategies.adversarial.run_agent", side_effect=mock_agent), \
             patch("emdx.workflows.strategies.adversarial.resolve_template", side_effect=lambda t, c: t), \
             patch("emdx.workflows.strategies.adversarial.document_service") as mock_docs:

            mock_db.create_individual_run.side_effect = [1, 2, 3]
            mock_docs.get_document.return_value = {'content': 'phase output', 'title': 'Phase'}

            executor = MagicMock()
            result = await strategy.execute(
                stage_run_id=1, stage=stage, context={},
                stage_input="topic", executor=executor,
            )

            assert result.success is True
            assert run_count == 3
            assert len(result.individual_outputs) == 3
            # Last output is the synthesis
            assert result.synthesis_doc_id == result.output_doc_id
