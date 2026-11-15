"""flow 包：流程图模型、节点注册表、执行引擎（可视化工作台内核）。

对外接口：
- 图：Graph / validate_graph / topo_order / order_for_mode / default_graph
- 节点：NodeTypeRegistry / load_node_types / NodeContext / NodeResult
- 执行：Runner / run_flow
- 存储：store 子模块（项目 00_project/workflows/）
"""
from .graph import (
    PORT_COMPAT,
    STAGE_ORDER,
    Edge,
    FlowError,
    Graph,
    Node,
    ancestors,
    default_graph,
    order_for_mode,
    port_compatible,
    topo_order,
    validate_graph,
)
from .nodes import NodeContext, NodeError, NodeResult
from .registry import NodeType, NodeTypeRegistry, load_node_types, parse_node_types
from .compare import compare_runs, format_compare_text
from .conditions import ConditionError, evaluate
from .locks import LockError, log_transaction, state_lock
from .replay import build_replay, format_replay_text
from .runner import Runner, recover_run, run_flow
from .templates import (
    TemplateError,
    get_template,
    instantiate,
    instantiate_template,
    load_templates,
)
from .store import (
    graph_path,
    list_baselines,
    list_graphs,
    list_runs,
    read_graph_data,
    read_run,
    resolve_project,
    runs_dir,
    set_baseline,
    clear_baseline,
    get_baseline,
    workflows_dir,
    write_graph_data,
    write_run,
)
from .artifacts import (
    collect_files,
    create_snapshot,
    diff_files,
    diff_snapshots,
    diff_with_current,
    format_diff_text,
    latest_snapshot,
    list_snapshots,
    read_snapshot,
)

__all__ = [
    "PORT_COMPAT",
    "STAGE_ORDER",
    "Edge",
    "FlowError",
    "Graph",
    "Node",
    "NodeContext",
    "NodeError",
    "NodeResult",
    "NodeType",
    "NodeTypeRegistry",
    "Runner",
    "ancestors",
    "build_replay",
    "default_graph",
    "format_replay_text",
    "LockError",
    "log_transaction",
    "state_lock",
    "ConditionError",
    "evaluate",
    "format_compare_text",
    "compare_runs",
    "graph_path",
    "list_graphs",
    "load_node_types",
    "order_for_mode",
    "parse_node_types",
    "port_compatible",
    "read_graph_data",
    "read_run",
    "resolve_project",
    "run_flow",
    "runs_dir",
    "topo_order",
    "validate_graph",
    "workflows_dir",
    "write_graph_data",
    "write_run",
    "list_runs",
    "recover_run",
    "list_baselines",
    "set_baseline",
    "clear_baseline",
    "get_baseline",
    "collect_files",
    "create_snapshot",
    "diff_files",
    "diff_snapshots",
    "diff_with_current",
    "format_diff_text",
    "latest_snapshot",
    "list_snapshots",
    "read_snapshot",
    "TemplateError",
    "get_template",
    "instantiate",
    "instantiate_template",
    "load_templates",
]
