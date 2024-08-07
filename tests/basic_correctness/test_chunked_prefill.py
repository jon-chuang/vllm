"""Compare the outputs of HF and vLLM when using greedy sampling.

It tests chunked prefill. Chunked prefill can be enabled by
enable_chunked_prefill=True. If prefill size exceeds max_num_batched_tokens,
prefill requests are chunked.

Run `pytest tests/models/test_chunked_prefill.py`.
"""
import pytest

from ..models.utils import check_logprobs_close, check_outputs_equal

MODELS = [
    "facebook/opt-125m",
    "meta-llama/Llama-2-7b-hf",
]

FP8_MODELS = [
    # does not work - CUDA illegal memory access - undiagnosed
    # "facebook/opt-125m",
    "nm-testing/Qwen2-1.5B-Instruct-FP8-K-V",
    "nm-testing/TinyLlama-1.1B-compressed-tensors-kv-cache-scheme"
]


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("dtype", ["half"])
@pytest.mark.parametrize("max_tokens", [32])
@pytest.mark.parametrize("chunked_prefill_token_size", [1, 4, 16])
@pytest.mark.parametrize("enforce_eager", [False, True])
# NOTE: Increasing this in this suite will fail CI because we currently cannot
# reset distributed env properly. Use a value > 1 just when you test.
@pytest.mark.parametrize("tensor_parallel_size", [1])
def test_models(
    hf_runner,
    vllm_runner,
    example_prompts,
    model: str,
    dtype: str,
    max_tokens: int,
    chunked_prefill_token_size: int,
    enforce_eager: bool,
    tensor_parallel_size: int,
) -> None:
    max_num_seqs = min(chunked_prefill_token_size, 256)
    enable_chunked_prefill = False
    max_num_batched_tokens = None
    if chunked_prefill_token_size != -1:
        enable_chunked_prefill = True
        max_num_batched_tokens = chunked_prefill_token_size

    with hf_runner(model, dtype=dtype) as hf_model:
        hf_outputs = hf_model.generate_greedy(example_prompts, max_tokens)

    with vllm_runner(
            model,
            dtype=dtype,
            max_num_batched_tokens=max_num_batched_tokens,
            enable_chunked_prefill=enable_chunked_prefill,
            tensor_parallel_size=tensor_parallel_size,
            enforce_eager=enforce_eager,
            max_num_seqs=max_num_seqs,
    ) as vllm_model:
        vllm_outputs = vllm_model.generate_greedy(example_prompts, max_tokens)

    check_outputs_equal(
        outputs_0_lst=hf_outputs,
        outputs_1_lst=vllm_outputs,
        name_0="hf",
        name_1="vllm",
    )


@pytest.mark.parametrize("model", FP8_MODELS)
@pytest.mark.parametrize("kv_cache_dtype", ["fp8"])
@pytest.mark.parametrize("max_tokens", [512])
@pytest.mark.parametrize("chunked_prefill_token_size", [1, 4, 16])
@pytest.mark.parametrize("enforce_eager", [False, True])
# NOTE: Increasing this in this suite will fail CI because we currently cannot
# reset distributed env properly. Use a value > 1 just when you test.
@pytest.mark.parametrize("tensor_parallel_size", [1])
def test_fp8_kv_cache(
    vllm_runner,
    example_prompts,
    example_long_prompts,
    model: str,
    kv_cache_dtype: str,
    max_tokens: int,
    chunked_prefill_token_size: int,
    enforce_eager: bool,
    tensor_parallel_size: int,
) -> None:
    NUM_LOG_PROBS = 8
    NUM_OUTPUT_TOKENS = 4

    max_num_seqs = min(chunked_prefill_token_size, 256)
    enable_chunked_prefill = False
    max_num_batched_tokens = None
    if chunked_prefill_token_size != -1:
        enable_chunked_prefill = True
        max_num_batched_tokens = chunked_prefill_token_size

    with vllm_runner(
            model,
            tensor_parallel_size=tensor_parallel_size,
            enforce_eager=enforce_eager,
            max_num_seqs=max_num_seqs,
            kv_cache_dtype=kv_cache_dtype,
    ) as vllm_model:
        decode_outputs = vllm_model.generate_greedy_logprobs(
            example_prompts + example_long_prompts, max_tokens, NUM_LOG_PROBS)

    with vllm_runner(
            model,
            max_num_batched_tokens=max_num_batched_tokens,
            enable_chunked_prefill=enable_chunked_prefill,
            tensor_parallel_size=tensor_parallel_size,
            enforce_eager=enforce_eager,
            max_num_seqs=max_num_seqs,
            kv_cache_dtype=kv_cache_dtype,
    ) as vllm_model:
        chunked_prefill_outputs = vllm_model.generate_greedy_logprobs(
            example_prompts + example_long_prompts, max_tokens, NUM_LOG_PROBS)

    check_logprobs_close(
        outputs_0_lst=decode_outputs[:NUM_OUTPUT_TOKENS],
        outputs_1_lst=chunked_prefill_outputs[:NUM_OUTPUT_TOKENS],
        name_0="decode",
        name_1="chunked_prefill",
    )
