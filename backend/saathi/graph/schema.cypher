// Dependency graph schema for the Saathi pilot.
// Mirrors DEFAULT_EDGES / CO_LOCATABLE in dependencies.py. Keep the two in sync;
// tests/test_dependencies.py asserts the in-memory graph matches this file's shape.

CREATE CONSTRAINT step_kind_unique IF NOT EXISTS
FOR (s:Step) REQUIRE s.kind IS UNIQUE;

MERGE (consult:Step          {kind: 'consult',           travel: true});
MERGE (biopsy:Step           {kind: 'biopsy',            travel: true});
MERGE (bloods:Step           {kind: 'bloods',            travel: true});
MERGE (scan:Step             {kind: 'scan',              travel: true});
MERGE (path:Step             {kind: 'pathology_report',  travel: false});
MERGE (rad:Step              {kind: 'radiology_report',  travel: false});
MERGE (review:Step           {kind: 'review_consult',    travel: true});
MERGE (treatment:Step        {kind: 'treatment',         travel: true});

// (a)-[:REQUIRED_BY]->(b) means "b cannot usefully happen until a is done".
MATCH (a:Step {kind: 'consult'}),          (b:Step {kind: 'biopsy'})           MERGE (a)-[:REQUIRED_BY]->(b);
MATCH (a:Step {kind: 'consult'}),          (b:Step {kind: 'bloods'})           MERGE (a)-[:REQUIRED_BY]->(b);
MATCH (a:Step {kind: 'consult'}),          (b:Step {kind: 'scan'})             MERGE (a)-[:REQUIRED_BY]->(b);
MATCH (a:Step {kind: 'biopsy'}),           (b:Step {kind: 'pathology_report'}) MERGE (a)-[:REQUIRED_BY]->(b);
MATCH (a:Step {kind: 'scan'}),             (b:Step {kind: 'radiology_report'}) MERGE (a)-[:REQUIRED_BY]->(b);
MATCH (a:Step {kind: 'pathology_report'}), (b:Step {kind: 'review_consult'})   MERGE (a)-[:REQUIRED_BY]->(b);
MATCH (a:Step {kind: 'radiology_report'}), (b:Step {kind: 'review_consult'})   MERGE (a)-[:REQUIRED_BY]->(b);
MATCH (a:Step {kind: 'bloods'}),           (b:Step {kind: 'review_consult'})   MERGE (a)-[:REQUIRED_BY]->(b);
MATCH (a:Step {kind: 'review_consult'}),   (b:Step {kind: 'treatment'})        MERGE (a)-[:REQUIRED_BY]->(b);

// Undirected in practice; queries match on either direction.
MATCH (a:Step {kind: 'consult'}), (b:Step {kind: 'biopsy'})         MERGE (a)-[:CO_LOCATABLE]->(b);
MATCH (a:Step {kind: 'consult'}), (b:Step {kind: 'bloods'})         MERGE (a)-[:CO_LOCATABLE]->(b);
MATCH (a:Step {kind: 'biopsy'}),  (b:Step {kind: 'bloods'})         MERGE (a)-[:CO_LOCATABLE]->(b);
MATCH (a:Step {kind: 'scan'}),    (b:Step {kind: 'review_consult'}) MERGE (a)-[:CO_LOCATABLE]->(b);
MATCH (a:Step {kind: 'bloods'}),  (b:Step {kind: 'review_consult'}) MERGE (a)-[:CO_LOCATABLE]->(b);
