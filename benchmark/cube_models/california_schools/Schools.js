cube(`Schools`, {
  sql: `SELECT * FROM bird.schools`,
  joins: {
    Satscores: { sql: `${CUBE}."CDSCode" = ${Satscores}.cds`, relationship: `hasOne` },
    Frpm: { sql: `${CUBE}."CDSCode" = ${Frpm}."CDSCode"`, relationship: `hasOne` },
  },
  measures: {
    schoolCount: { sql: `"CDSCode"`, type: `count` },
  },
  dimensions: {
    cdsCode: { sql: `"CDSCode"`, type: `string`, primaryKey: true },
    statusType: {
      sql: `"StatusType"`, type: `string`,
      description: "School operational status. Values: Active = operating, Closed = permanently closed, Merged = merged into another school, Pending.",
    },
    county: { sql: `"County"`, type: `string`, description: "County name (e.g. Alameda, Los Angeles, Fresno)." },
    district: { sql: `"District"`, type: `string` },
    school: { sql: `"School"`, type: `string` },
    city: { sql: `"City"`, type: `string` },
    zip: { sql: `"Zip"`, type: `string` },
    charter: {
      sql: `"Charter"`, type: `string`,
      description: "Charter school flag: 1 = charter school (特许学校), 0 = non-charter.",
    },
    fundingType: {
      sql: `"FundingType"`, type: `string`,
      description: "Funding source type: Directly funded = state directly funded charter, Locally funded = locally funded.",
    },
    street: { sql: `"Street"`, type: `string` },
    phone: { sql: `"Phone"`, type: `string` },
    socType: {
      sql: `"SOCType"`, type: `string`,
      description: "Public K-12 school operation category, e.g. comprehensive high school, special education school, continuation high school, juvenile court school, Youth Authority Facilities. Codes in sibling column SOC.",
    },
    edOpsName: {
      sql: `"EdOpsName"`, type: `string`,
      description: "Educational option name, e.g. State Special School (EdOpsCode=SSS), Special Education Consortia (SPECON).",
    },
    virtual: {
      sql: `"Virtual"`, type: `string`,
      description: "Instruction mode: F = fully virtual (fully remote), P = partially virtual, N = non-virtual traditional campus. (Verified against BIRD evidence: exclusively virtual means Virtual='F'.)",
    },
    magnet: {
      sql: `"Magnet"`, type: `string`,
      description: "Magnet school or offers a magnet program: 1 = yes, 0 = no.",
    },
  },
});
