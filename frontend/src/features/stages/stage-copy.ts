import contractSnapshot from "../../../contracts/capabilities.json";
import type { components } from "../../api/generated";

export type Stage = components["schemas"]["Stage"];
export type StageContract = components["schemas"]["StageContract"];

export const stageOrder = ["planner", "designer", "builder", "reviewer", "deployer"] as const;

interface StageCopy {
  displayName: string;
  goal: string;
  sections: readonly string[];
}

export const stageCopy: Record<Stage, StageCopy> = {
  planner: {
    displayName: "Planner",
    goal: "明确目标、用户、范围、验收标准、风险、开放问题和决策。",
    sections: ["目标与用户", "场景与需求", "范围与非目标", "验收与风险", "开放问题与决策"],
  },
  designer: {
    displayName: "Designer",
    goal: "形成架构、模块、数据、API、事件、错误、安全约束和可执行构建任务。",
    sections: ["架构与模块", "数据与 API", "事件与错误", "安全与约束", "构建任务"],
  },
  builder: {
    displayName: "Builder",
    goal: "实现已批准范围，并记录文件、测试、构建结果、限制、偏差和剩余问题。",
    sections: ["实现范围", "文件与改动", "测试与构建", "限制与偏差", "剩余问题"],
  },
  reviewer: {
    displayName: "Reviewer",
    goal: "基于证据审查阻断问题、重要问题、建议、结论和返工目标。",
    sections: ["审查范围", "证据", "阻断与重要问题", "建议与结论", "返工目标"],
  },
  deployer: {
    displayName: "Deployer",
    goal: "准备版本、环境、配置、安装、运行、健康检查、日志、回滚和已知问题文档。",
    sections: ["版本与环境", "配置与前置条件", "安装与运行", "健康检查与日志", "回滚与已知问题"],
  },
};

const typedSnapshot = contractSnapshot as unknown as {
  stageContracts: StageContract[];
};

export function stageContract(stage: Stage): StageContract {
  const contract = typedSnapshot.stageContracts.find((candidate) => candidate.stage === stage);
  if (contract === undefined) {
    throw new Error(`Missing frozen StageContract for ${stage}`);
  }
  return contract;
}

export function isStage(value: string): value is Stage {
  return (stageOrder as readonly string[]).includes(value);
}
