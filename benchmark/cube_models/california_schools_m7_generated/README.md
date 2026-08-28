# M7 生成器产出（含 LLM 描述/别名，当前 live 版）

由 `datus generate-cube-models --datasource bird_sqlite --tables schools,frpm,satscores`
生成，后经三轮迭代手工注入/修正：SOC/Charter 编码列语义、
Frpm.eligibleFreeRate{K12,Ages517} 行级比率字段（含哨兵 -1）。
这是当前 cube-live 容器挂载的同版本快照。

重启机器后恢复：把本目录挂为 cube 容器的 /cube/conf/model，
数据视图 public.{schools,frpm,satscores} 指向 bird schema（见上层 README）。
