cube(`Orders`, {
  sql: `SELECT * FROM orders`,
  measures: {
    count: { sql: `id`, type: `count` },
    totalAmount: { sql: `amount`, type: `sum`, title: `Total Amount` },
  },
  dimensions: {
    status: { sql: `status`, type: `string` },
    region: { sql: `region`, type: `string` },
    createdAt: { sql: `created_at`, type: `time` },
  },
});
