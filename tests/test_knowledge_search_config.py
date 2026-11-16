"""M27：检索配置（权重/同义词/停用词）与混合排序增强。"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from cli.main import main as cli_main  # noqa: E402
from knowledge_service import (  # noqa: E402
    KnowledgeIndexError,
    build_index,
    load_search_config,
    search_index,
    search_index_card,
)
from knowledge_service.index_builder import (  # noqa: E402
    SEARCH_CONFIG_SCHEMA,
    _merge_weights,
    _query_term_weights,
    _query_terms,
    _rank_candidate,
    normalize_query_text,
)


def _write_config(path: Path, *, weights=None, synonyms=None, stopwords=None, expand_limit=8) -> None:
    data = {
        "contract_version": "0.1",
        "weights": weights
        or {"heading": 2.0, "path": 1.0, "phrase": 1.5, "coverage": 1.0},
        "synonyms": synonyms or {},
        "stopwords": stopwords or [],
        "expand_limit": expand_limit,
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class SearchConfigTest(unittest.TestCase):
    """配置加载/校验与查询归一。"""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="wb_kbcfg_")
        self.root = Path(self._tmp)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_default_config_loaded_from_content(self) -> None:
        config = load_search_config()
        self.assertEqual("0.1", config["contract_version"])
        self.assertEqual(
            {"heading": 2.0, "path": 1.0, "phrase": 1.5, "coverage": 1.0},
            config["weights"],
        )
        self.assertGreaterEqual(len(config["synonyms"]), 5)
        self.assertGreaterEqual(len(config["stopwords"]), 5)
        self.assertEqual(8, config["expand_limit"])

    def test_custom_config_path_loaded(self) -> None:
        path = self.root / "search.json"
        _write_config(
            path,
            weights={"heading": 4.0, "path": 0.0, "phrase": 1.0, "coverage": 0.5},
            synonyms={"悬念": ["悬疑"]},
            stopwords=["的"],
            expand_limit=3,
        )
        config = load_search_config(path)
        self.assertEqual(4.0, config["weights"]["heading"])
        self.assertEqual(["悬疑"], config["synonyms"]["悬念"])
        self.assertEqual(["的"], config["stopwords"])

    def test_config_schema_registered(self) -> None:
        schema_path = REPO_ROOT / "packages" / "contracts" / "schemas" / SEARCH_CONFIG_SCHEMA
        self.assertTrue(schema_path.is_file())

    def test_invalid_config_rejected(self) -> None:
        path = self.root / "bad.json"
        path.write_text(json.dumps({"contract_version": "0.1"}), encoding="utf-8")
        with self.assertRaises(KnowledgeIndexError) as ctx:
            load_search_config(path)
        self.assertIn("契约校验失败", str(ctx.exception))

    def test_invalid_json_rejected(self) -> None:
        path = self.root / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(KnowledgeIndexError):
            load_search_config(path)

    def test_missing_config_path_rejected(self) -> None:
        with self.assertRaises(KnowledgeIndexError) as ctx:
            load_search_config(self.root / "missing.json")
        self.assertIn("不存在", str(ctx.exception))

    def test_merge_weights_validation(self) -> None:
        self.assertEqual(3.0, _merge_weights({"heading": 3})["heading"])
        with self.assertRaises(KnowledgeIndexError):
            _merge_weights({"unknown": 1.0})
        with self.assertRaises(KnowledgeIndexError):
            _merge_weights({"heading": -1})
        with self.assertRaises(KnowledgeIndexError):
            _merge_weights({"heading": "fast"})

    def test_normalize_query_text(self) -> None:
        self.assertEqual("悬念 设计", normalize_query_text("  悬念　　设计  "))
        self.assertEqual("ABC", normalize_query_text("ＡＢＣ"))

    def test_query_terms_expands_synonyms_and_filters_stopwords(self) -> None:
        config = {"synonyms": {"悬念": ["悬疑"]}, "stopwords": ["的"], "expand_limit": 8}
        terms = _query_terms("的悬念设计", config)
        self.assertIn("悬念", terms)
        self.assertIn("悬疑", terms)
        self.assertNotIn("的", terms)

    def test_rank_candidate_weights_change_score(self) -> None:
        base = _rank_candidate(
            "悬念", "02_方法.md", "悬念方法", "建立悬念的三种方法", 1.0
        )
        low = _rank_candidate(
            "悬念",
            "02_方法.md",
            "悬念方法",
            "建立悬念的三种方法",
            1.0,
            weights={"heading": 0.0, "path": 0.0, "phrase": 0.0, "coverage": 0.0},
        )
        self.assertGreater(base, low)

    def test_query_term_weights_mark_synonyms(self) -> None:
        config = {
            "synonyms": {"悬念": ["悬疑"]},
            "stopwords": [],
            "expand_limit": 8,
            "synonym_weight": 0.3,
        }
        weights = _query_term_weights("悬念", config)
        self.assertEqual(1.0, weights["悬念"])
        self.assertEqual(0.3, weights["悬疑"])

    def test_synonym_weight_loaded_and_validated(self) -> None:
        path = self.root / "search-weighted.json"
        _write_config(path, synonyms={"悬念": ["悬疑"]})
        data = json.loads(path.read_text(encoding="utf-8"))
        data["synonym_weight"] = 0.2
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(0.2, load_search_config(path)["synonym_weight"])

        bad = self.root / "search-bad-weight.json"
        data["synonym_weight"] = 2
        bad.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(KnowledgeIndexError):
            load_search_config(bad)


class HybridConfigIndexTest(unittest.TestCase):
    """建索引后验证同义词检索、权重覆盖与 CLI/服务接入。"""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="wb_kbhybcfg_")
        self.root = Path(self._tmp)
        self.source = self.root / "kb"
        self.out = self.root / "index"
        self.source.mkdir(parents=True)
        (self.source / "01_故事.md").write_text(
            "# 开头\n\n开场建立悬念，主角雨夜收到一封信。\n", encoding="utf-8"
        )
        (self.source / "02_方法.md").write_text(
            "# 悬疑方法\n\n用信息差和倒计时制造悬疑。\n", encoding="utf-8"
        )
        build_index(self.source, self.out)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _config(self, *, synonyms=None, weights=None) -> dict:
        return {
            "contract_version": "0.1",
            "weights": weights
            or {"heading": 2.0, "path": 1.0, "phrase": 1.5, "coverage": 1.0},
            "synonyms": synonyms if synonyms is not None else {"悬念": ["悬疑"]},
            "stopwords": [],
            "expand_limit": 8,
        }

    def test_synonym_config_enables_cross_term_hit(self) -> None:
        with_syn = search_index(self.out, "悬念", mode="hybrid", config=self._config())
        paths = {item["path"] for item in with_syn["results"]}
        self.assertIn("02_方法.md", paths)
        self.assertIn("悬疑", with_syn["variants"])

        without = search_index(
            self.out, "悬念", mode="hybrid", config=self._config(synonyms={})
        )
        plain_paths = {item["path"] for item in without["results"]}
        self.assertNotIn("02_方法.md", plain_paths)

    def test_zero_weights_flatten_scores(self) -> None:
        zero = {"heading": 0.0, "path": 0.0, "phrase": 0.0, "coverage": 0.0}
        result = search_index(
            self.out, "悬念", mode="hybrid", config=self._config(weights=zero)
        )
        self.assertTrue(result["results"])
        for item in result["results"]:
            self.assertEqual(1.0, item["score"])
        self.assertEqual(zero, result["weights"])

    def test_cli_weights_override(self) -> None:
        code = cli_main(
            [
                "index", "search", "--query", "悬念",
                "--out", str(self.out), "--mode", "hybrid",
                "--weights", "heading=0,path=0,phrase=0,coverage=0", "--json",
            ]
        )
        self.assertEqual(0, code)

    def test_cli_invalid_weight_key(self) -> None:
        code = cli_main(
            [
                "index", "search", "--query", "悬念", "--out", str(self.out),
                "--weights", "bogus=1", "--json",
            ]
        )
        self.assertEqual(1, code)

    def test_cli_invalid_weights_format(self) -> None:
        code = cli_main(
            [
                "index", "search", "--query", "悬念", "--out", str(self.out),
                "--weights", "heading", "--json",
            ]
        )
        self.assertEqual(1, code)

    def test_service_report_includes_search_config(self) -> None:
        result = search_index_card(
            "测试项目",
            "01",
            "开场如何建立悬念",
            ["悬念"],
            index_dir=str(self.out),
        )
        self.assertEqual("ok", result["status"])
        report = result["report"]
        self.assertIn("search_config", report)
        self.assertEqual(2.0, report["search_config"]["weights"]["heading"])
        self.assertGreaterEqual(report["search_config"]["synonyms"], 0)

    def test_synonym_weight_pushes_expanded_match_down(self) -> None:
        config = self._config()
        config["synonym_weight"] = 0.2
        result = search_index(self.out, "悬念", mode="hybrid", config=config)
        self.assertEqual(0.2, result["synonym_weight"])
        self.assertEqual(0.2, result["term_weights"]["悬疑"])
        scores = {item["path"]: item["score"] for item in result["results"]}
        self.assertIn("01_故事.md", scores)
        self.assertIn("02_方法.md", scores)
        self.assertGreater(scores["01_故事.md"], scores["02_方法.md"])

    def test_service_custom_config_changes_evidence(self) -> None:
        no_syn = self._config(synonyms={})
        result = search_index_card(
            "测试项目",
            "01",
            "开场如何建立悬念",
            ["悬念"],
            index_dir=str(self.out),
            search_config=no_syn,
        )
        paths = {item["path"] for item in result["card"]["evidence"]}
        self.assertNotIn("02_方法.md", paths)


class SearchLimitsTest(unittest.TestCase):
    """M30：min_score / max_per_file / snippet_chars / proximity_weight。"""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="wb_kblimits_")
        self.root = Path(self._tmp)
        self.source = self.root / "kb"
        self.out = self.root / "index"
        self.source.mkdir(parents=True)
        (self.source / "01_碎片.md").write_text(
            "# 悬念开场\n\n建立悬念：第一幕用反常细节制造疑问。\n\n"
            "# 另一段\n\n悬念升级：第二幕用误会加深紧张。\n",
            encoding="utf-8",
        )
        (self.source / "02_参考.md").write_text(
            "# 参考\n\n悬念与反转在第三幕同时出现。\n", encoding="utf-8"
        )
        build_index(self.source, self.out)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _config(self, **extra) -> dict:
        base = {
            "contract_version": "0.1",
            "weights": {"heading": 2.0, "path": 1.0, "phrase": 1.5, "coverage": 1.0},
            "synonyms": {},
            "stopwords": [],
            "expand_limit": 8,
        }
        base.update(extra)
        return base

    def test_default_config_includes_m30_fields(self) -> None:
        config = load_search_config()
        self.assertEqual(0.0, config["min_score"])
        self.assertEqual(2, config["max_per_file"])
        self.assertEqual(120, config["snippet_chars"])
        self.assertAlmostEqual(0.5, config["proximity_weight"])

    def test_max_per_file_limits_same_file(self) -> None:
        config = self._config(max_per_file=1, snippet_chars=40, proximity_weight=0.0)
        result = search_index(self.out, "悬念", mode="hybrid", config=config)
        self.assertEqual(1, result["max_per_file"])
        same_file = [item for item in result["results"] if item["path"] == "01_碎片.md"]
        self.assertLessEqual(len(same_file), 1)

    def test_snippet_chars_truncates(self) -> None:
        config = self._config(snippet_chars=40, max_per_file=5)
        result = search_index(self.out, "悬念", mode="hybrid", config=config)
        self.assertTrue(result["results"])
        for item in result["results"]:
            self.assertLessEqual(len(item["snippet"]), 41)

    def test_min_score_filters_results(self) -> None:
        config = self._config(min_score=999.0)
        result = search_index(self.out, "悬念", mode="hybrid", config=config)
        self.assertEqual(0, result["count"])
        self.assertEqual([], result["results"])

    def test_proximity_score_prefers_adjacent_terms(self) -> None:
        from knowledge_service.index_builder import _proximity_score

        near = _proximity_score("悬念反转相邻出现", {"悬念": 1.0, "反转": 1.0})
        far = _proximity_score(
            "悬念" + "填充内容" * 20 + "反转", {"悬念": 1.0, "反转": 1.0}
        )
        self.assertGreater(near, far)
        self.assertGreater(near, 0.0)
        self.assertLessEqual(near, 1.0)
        self.assertEqual(0.0, _proximity_score("悬念", {"悬念": 1.0}))

    def test_proximity_weight_changes_hybrid_scores(self) -> None:
        plain = self._config(proximity_weight=0.0)
        boosted = {**plain, "proximity_weight": 2.0}
        low = search_index(self.out, "悬念", mode="hybrid", config=plain)
        high = search_index(self.out, "悬念", mode="hybrid", config=boosted)
        self.assertGreaterEqual(
            max(item["score"] for item in high["results"]),
            max(item["score"] for item in low["results"]),
        )

    def test_cli_min_score_and_max_per_file(self) -> None:
        code = cli_main(
            [
                "index", "search", "--query", "悬念", "--out", str(self.out),
                "--min-score", "999", "--json",
            ]
        )
        self.assertEqual(0, code)
        code = cli_main(
            [
                "index", "search", "--query", "悬念", "--out", str(self.out),
                "--max-per-file", "1", "--json",
            ]
        )
        self.assertEqual(0, code)

    def test_service_report_includes_m30_fields(self) -> None:
        config = self._config(
            min_score=0.0, max_per_file=1, snippet_chars=40, proximity_weight=0.0
        )
        result = search_index_card(
            "演示项目", "01", "建立悬念", ["悬念"],
            index_dir=str(self.out), search_config=config,
        )
        report_cfg = result["report"]["search_config"]
        self.assertEqual(1, report_cfg["max_per_file"])
        self.assertEqual(40, report_cfg["snippet_chars"])
        self.assertEqual(0.0, report_cfg["proximity_weight"])

    def test_invalid_m30_config_rejected(self) -> None:
        path = self.root / "bad-m30.json"
        data = self._config()
        data["max_per_file"] = 99
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(KnowledgeIndexError):
            load_search_config(path)


if __name__ == "__main__":
    unittest.main()
