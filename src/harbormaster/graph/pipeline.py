"""Pipeline definition with optional pilot interrupt + full-corpus runner."""

from __future__ import annotations

import threading
from uuid import uuid4

from harbormaster.graph import nodes
from harbormaster.graph.state import PipelineState
from harbormaster.ingest.loader_adapter import LoaderAdapter
from harbormaster.ledger.store import LedgerStore
from harbormaster.models import Category, ComparisonStatus, EmailMessage, EmailVerdict, RunRequest, RunResult, is_demo_email_id
from harbormaster.report.submission import write_submission


def run_pipeline(
    email: EmailMessage,
    *,
    degrade: bool = False,
    chaos: list[str] | None = None,
    rules_only: bool = False,
    two_value: bool = False,
    save_board: bool = True,
) -> RunResult:
    state = PipelineState(
        email=email,
        degrade=degrade,
        chaos=list(chaos or []),
        rules_only=rules_only,
        two_value=two_value,
        save_board=save_board,
    )
    for step in (nodes.node_chaos, nodes.node_scout, nodes.node_reader, nodes.node_court, nodes.node_report):
        state = step(state)
    assert state.card
    return RunResult(
        run_id=state.card.case_id,
        card=state.card,
        transcript=state.transcript,
        submission=state.submission,
        official=state.official,
    )


def run_from_request(req: RunRequest) -> RunResult:
    loader = LoaderAdapter()
    source = req.source
    if not req.email_id:
        ids = loader.list_email_ids(source=source)
        if not ids:
            raise FileNotFoundError("no emails in inbox")
        email_id = ids[0]
    else:
        email_id = req.email_id
    email = loader.load(email_id, source=source)
    two_value = req.two_value if req.two_value is not None else False
    save_board = req.save_board if req.save_board is not None else True
    return run_pipeline(
        email,
        degrade=req.degrade,
        chaos=req.chaos,
        rules_only=req.rules_only,
        two_value=two_value,
        save_board=save_board,
    )


def run_corpus(
    *,
    source: str = "auto",
    rules_only: bool = False,
    two_value: bool = True,
    save_board: bool = False,
    degrade: bool = False,
    progress: callable | None = None,
    email_ids: list[str] | None = None,
    skip_ids: list[str] | None = None,
) -> dict:
    loader = LoaderAdapter()
    ids = list(email_ids) if email_ids is not None else loader.required_email_ids(source=source)
    if skip_ids:
        skip = set(skip_ids)
        ids = [i for i in ids if i not in skip]
    if not ids:
        raise FileNotFoundError("no email ids from inbox or local data")
    results: dict[str, EmailVerdict] = {}
    errors: dict[str, str] = {}
    for i, email_id in enumerate(ids, start=1):
        try:
            email = loader.load(email_id)
            result = run_pipeline(
                email,
                degrade=degrade or rules_only,
                rules_only=rules_only,
                two_value=two_value,
                save_board=save_board or is_demo_email_id(email_id),
            )
            assert result.official
            results[email_id] = result.official
        except Exception as exc:  # noqa: BLE001 — corpus must cover every id
            errors[email_id] = str(exc)
            results[email_id] = EmailVerdict(category=Category.GENERAL, status=ComparisonStatus.OK)
        if progress:
            progress(i, len(ids), email_id)
    out_path = _write_best_submission(loader, results, ids)
    try:
        from harbormaster.compute.worker import offload_bytes

        offload_bytes("exports/submission.json", out_path.read_bytes(), "application/json")
    except Exception:
        pass
    return {
        "count": len(results),
        "errors": errors,
        "path": str(out_path),
        "email_ids": ids,
    }


def start_corpus_job(
    *,
    source: str = "auto",
    rules_only: bool = False,
    two_value: bool = True,
    save_board: bool = False,
    degrade: bool = True,
    email_ids: list[str] | None = None,
    skip_ids: list[str] | None = None,
) -> str:
    job_id = uuid4().hex
    store = LedgerStore()
    store.save_job(job_id, "queued", 0, 0)

    def _run() -> None:
        store.save_job(job_id, "running", 0, 0)
        try:
            def progress(i: int, total: int, _eid: str) -> None:
                store.save_job(job_id, "running", total, i)

            out = run_corpus(
                source=source,
                rules_only=rules_only,
                two_value=two_value,
                save_board=save_board,
                degrade=degrade,
                progress=progress,
                email_ids=email_ids,
                skip_ids=skip_ids,
            )
            store.save_job(job_id, "done", out["count"], out["count"], payload=out)
        except Exception as exc:  # noqa: BLE001
            store.save_job(job_id, "error", 0, 0, error=str(exc))

    threading.Thread(target=_run, name=f"hm-corpus-{job_id[:8]}", daemon=True).start()
    return job_id


def pick_seed_ids(loader: LoaderAdapter | None = None, *, compare: int = 10, other: int = 8) -> list[str]:
    loader = loader or LoaderAdapter()
    demos = [i for i in loader.list_email_ids(source="local") if is_demo_email_id(i)]
    with_docs: list[str] = []
    without: list[str] = []
    for email_id in loader.list_email_ids(source="official"):
        try:
            email = loader.load(email_id)
        except FileNotFoundError:
            continue
        n = len(email.attachments) or len(email.attachment_paths)
        if n >= 2 and len(with_docs) < compare:
            with_docs.append(email_id)
        elif n == 0 and len(without) < other:
            without.append(email_id)
        if len(with_docs) >= compare and len(without) >= other:
            break
    return demos + with_docs + without


def _write_best_submission(loader: LoaderAdapter, results: dict[str, EmailVerdict], ids: list[str]):
    store = LedgerStore()
    known = store.list_verdicts()
    required = []
    try:
        required = loader.required_email_ids()
    except Exception:
        required = []
    if required and all(eid in known or eid in results for eid in required):
        merged = {eid: known.get(eid) or results[eid] for eid in required if eid in known or eid in results}
        try:
            return write_submission(merged, required, _submission_path())
        except Exception:
            pass
    return write_submission(results, ids, _submission_path())


def _submission_path():
    from harbormaster.config import data_dir

    return data_dir() / "submission.json"
