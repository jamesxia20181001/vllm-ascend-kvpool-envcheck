#!/bin/bash
# stub/smoke_test.sh — 构建 stub 镜像并端到端验证检查器的预期判定计数。
#
# 把 stub/README.md 中声称的 PASS/MANUAL 计数固化为机器断言：任一计数偏离即失败。
# 4K 档位：A2 9 PASS / A3 单节点 9 PASS / A3 多节点 10 PASS+1 MANUAL
# 64K 档位：A2-64K 9 PASS / A3-64K 单节点 9 PASS / A3-64K 多节点 9 PASS+1 MANUAL（KERNEL 豁免）
#
# 用法：
#   bash stub/smoke_test.sh                # 构建（若镜像缺失）并跑全部场景
#   IMAGE=myimg bash stub/smoke_test.sh    # 用指定镜像名
#
# 前置：本机可运行 docker（需 --cap-add SYS_ADMIN 给 stub 的 /proc bind-mount）。
set -u

IMAGE="${IMAGE:-kvpool-envcheck-stub}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ASSERT="$HERE/assert_result.py"

CAPS="--cap-add SYS_ADMIN --security-opt apparmor=unconfined --security-opt seccomp=unconfined"

# 场景：name | profile | expected_pass | expected_manual | expected_exit | checker args...
scenes=(
  "a2-single-roce|a2|9|0|0|--hardware A2 --backend memcache --managed-memory-mb 32768 --deployment-mode single-node --link-type roce"
  "a3-single-hccs|a3|9|0|0|--hardware A3 --backend memcache --managed-memory-mb 32768 --deployment-mode single-node --link-type hccs"
  "a3-multi-hccs|a3|10|1|20|--hardware A3 --backend memcache --managed-memory-mb 32768 --deployment-mode multi-node --link-type hccs"
  "a2-64k-single-roce|a2-64k|9|0|0|--hardware A2 --backend memcache --managed-memory-mb 32768 --deployment-mode single-node --link-type roce"
  "a3-64k-single-hccs|a3-64k|9|0|0|--hardware A3 --backend memcache --managed-memory-mb 32768 --deployment-mode single-node --link-type hccs"
  "a3-64k-multi-hccs|a3-64k|9|1|20|--hardware A3 --backend memcache --managed-memory-mb 32768 --deployment-mode multi-node --link-type hccs"
)

command -v docker >/dev/null 2>&1 || { echo "错误：未找到 docker"; exit 2; }

# 镜像缺失则构建
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo ">> 镜像 $IMAGE 不存在，开始构建..."
  docker build -t "$IMAGE" -f "$HERE/Dockerfile" "$HERE/.." || { echo "构建失败"; exit 2; }
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
echo ">> 工作目录: $work"

passed=0
failed=0

run_scene() {
  local name="$1" profile="$2" exp_pass="$3" exp_manual="$4" exp_exit="$5" args="$6"
  local out="$work/$name"
  mkdir -p "$out"
  # 清理可能残留的结果文件（run_id 唯一，但重跑同目录会因文件已存在而报错）
  rm -f "$out"/*.result.json "$out"/*.report.txt

  echo ">> [$name] profile=$profile expect pass=$exp_pass manual=$exp_manual exit=$exp_exit"
  # 不用 set -e：多节点场景检查器合法退出 20
  docker run --rm $CAPS -e STUB_PROFILE="$profile" -v "$out:/tmp/out" "$IMAGE" \
    python3 kvpool_envcheck.py $args --output-dir /tmp/out \
    >/tmp/stub_smoke_"$name".log 2>&1
  local rc=$?

  local json
  json="$(ls "$out"/*.result.json 2>/dev/null | head -1)"
  if [ -z "$json" ]; then
    echo "   [FAIL] $name: 未生成 .result.json (docker rc=$rc)"
    echo "          日志: /tmp/stub_smoke_${name}.log"
    failed=$((failed + 1))
    return
  fi

  python3 "$ASSERT" "$json" "$exp_pass" "$exp_manual" "$exp_exit"
  local arc=$?
  # arc=0 断言通过；但 docker 退出码也应与 exp_exit 一致（已由 assert 覆盖 exit_code 字段）
  if [ "$arc" -eq 0 ]; then
    passed=$((passed + 1))
  else
    failed=$((failed + 1))
    echo "          docker rc=$rc; 日志: /tmp/stub_smoke_${name}.log"
  fi
}

for scene in "${scenes[@]}"; do
  IFS='|' read -r name profile ep em ee args <<<"$scene"
  run_scene "$name" "$profile" "$ep" "$em" "$ee" "$args"
done

echo ""
echo ">> 结果: $passed 通过, $failed 失败"
[ "$failed" -eq 0 ]
