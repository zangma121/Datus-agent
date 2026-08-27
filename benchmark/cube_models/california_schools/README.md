# california_schools Cube 模型（M5 实验资产）

四份 Cube 模型（Orders 为冒烟夹具；Schools/Frpm/Satscores 覆盖 BIRD
california_schools 三表，含 LLM 生成的维度/度量描述与行级计算字段
`Frpm.eligibleFreeRateK12`——两字段直接相除、无聚合，用于"最高/最低"
类问题按行排序；`Frpm.freeMealRateK12` 是 SUM/SUM 聚合比率，供县级
整体占比问题）。

## 一键起栈

```bash
docker network create cube-live-net
docker run -d --name cube-pg --network cube-live-net -p 15432:5432 \
  -e POSTGRES_USER=cube -e POSTGRES_PASSWORD=cube -e POSTGRES_DB=cube postgres:15-alpine
# 灌数据：.venv/bin/python 由 sqlite 导出 SQL 后 docker exec psql 导入
docker run -d --name cubestore-live --network cube-live-net -p 3030:3030 0fpy/cubestore:latest
docker run -d --name cube-live --network cube-live-net -p 4000:4000 \
  -v $(pwd)/benchmark/cube_models/california_schools:/cube/conf/model \
  -e CUBEJS_DB_TYPE=postgres -e CUBEJS_DB_HOST=cube-pg -e CUBEJS_DB_PORT=5432 \
  -e CUBEJS_DB_NAME=cube -e CUBEJS_DB_USER=cube -e CUBEJS_DB_PASS=cube \
  -e CUBEJS_API_SECRET=<your-secret> -e CUBEJS_DEV_MODE=false \
  -e CUBEJS_WEB_SOCKETS=false \
  -e CUBEJS_CUBESTORE_HOST=cubestore-live -e CUBEJS_CUBESTORE_PORT=3030 \
  cubejs/cube:latest
# 验证：
CUBE_LIVE_URL=http://localhost:4000 CUBE_LIVE_SECRET=<secret> \
  pytest tests/integration/tools/test_cube_adapter_live.py -q
```

注意：DEV_MODE=false 时改模型需 `docker restart cube-live` 生效。
描述注入：`benchmark/scripts/gen_cube_dim_desc.py`（抽样值 + LLM → description）。
