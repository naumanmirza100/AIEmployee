"""
Shared skill equivalences and related-terms for matching job keywords to CV skills.
Node.js ↔ JavaScript, React ↔ ReactJS, etc. Used by Lead Qualification and Summarization.
"""
from typing import Optional
from typing import Optional

SKILL_EQUIVALENCES = {
    # LLM / AI
    "llm": ["llms", "large language model", "language model"],
    "artificial intelligence": ["ai"],
    "machine learning": ["ml", "machine-learning", "deep learning", "neural networks"],
    "natural language processing": ["nlp"],
    "data science": ["data scientist", "datascience", "data analysis", "data analytics"],
    
    # C# / .NET Stack
    "c#": ["c sharp", "csharp", ".net", ".net framework", ".net core", ".net 5", ".net 6", ".net 7", ".net 8"],
    "c sharp": ["c#", "csharp", ".net", ".net framework", ".net core"],
    "csharp": ["c#", "c sharp", ".net", ".net framework", ".net core"],
    ".net": [".net framework", ".net core", ".net 5", ".net 6", ".net 7", ".net 8", "asp.net", "entity framework", "ef core", "linq", "wpf", "winforms", "blazor", "signalr"],
    ".net framework": [".net", ".net core", "asp.net", "entity framework", "wpf", "winforms"],
    ".net core": [".net", ".net framework", "asp.net core", "entity framework core", "ef core"],
    "asp.net": ["asp.net core", "asp.net mvc", "asp.net web api", "web api", ".net"],
    "asp.net core": ["asp.net", "asp.net mvc", "asp.net web api", "web api", ".net core"],
    "entity framework": ["ef", "ef core", "entity framework core", "entity framework 6", "code first", "database first"],
    "ef core": ["entity framework", "entity framework core", "ef"],
    
    # Python Stack
    "python": ["py", "python 3", "python 2", "django", "flask", "fastapi", "pyramid", "tornado", "bottle"],
    "py": ["python", "python 3"],
    "django": ["django rest framework", "drf", "django orm", "django channels", "python"],
    "django rest framework": ["drf", "django", "rest api"],
    "drf": ["django rest framework", "django"],
    "flask": ["flask-restful", "flask-sqlalchemy", "flask-migrate", "python"],
    "fastapi": ["fast api", "pydantic", "uvicorn", "python"],
    "numpy": ["python", "data science", "numerical computing"],
    "pandas": ["python", "data science", "data analysis"],
    "tensorflow": ["machine learning", "deep learning", "ml", "python"],
    "pytorch": ["machine learning", "deep learning", "ml", "python"],
    "scikit-learn": ["scikit learn", "sklearn", "machine learning", "ml", "python"],
    
    # JavaScript / Node.js Stack
    "node": ["node.js", "nodejs", "javascript", "js", "express", "express.js", "nestjs"],
    "node.js": ["nodejs", "javascript", "js", "express", "express.js", "nestjs", "koa", "hapi"],
    "nodejs": ["node.js", "javascript", "js", "express", "express.js"],
    "javascript": ["js", "ecmascript", "es6", "es7", "es8", "node.js", "nodejs", "typescript", "ts"],
    "js": ["javascript", "ecmascript", "node.js", "nodejs", "typescript", "ts"],
    "typescript": ["ts", "tsx", "typed javascript", "javascript"],
    "ts": ["typescript", "tsx", "javascript"],
    
    # Frontend Frameworks
    "react": ["react.js", "reactjs", "react native", "next.js", "nextjs", "gatsby", "redux", "mobx", "react hooks"],
    "react.js": ["react", "reactjs", "react native"],
    "reactjs": ["react", "react.js", "react native"],
    "react native": ["react", "rn", "mobile development"],
    "next.js": ["nextjs", "react", "ssr", "server side rendering"],
    "nextjs": ["next.js", "react"],
    "vue": ["vue.js", "vuejs", "vue 2", "vue 3", "nuxt.js", "nuxtjs", "vuex", "pinia"],
    "vue.js": ["vue", "vuejs", "nuxt.js"],
    "vuejs": ["vue", "vue.js"],
    "nuxt.js": ["nuxtjs", "vue", "ssr"],
    "angular": ["angularjs", "angular.js", "angular 2+", "angular cli", "rxjs", "typescript"],
    "angularjs": ["angular", "angular.js"],
    "angular.js": ["angular", "angularjs"],
    
    # Backend Frameworks
    "express": ["express.js", "expressjs", "express router", "middleware", "node.js", "nodejs"],
    "express.js": ["express", "expressjs", "node.js"],
    "expressjs": ["express", "express.js"],
    "nestjs": ["node.js", "typescript", "express"],
    
    # API Technologies
    "api": ["rest api", "restful", "graphql", "rest", "web api"],
    "rest api": ["rest", "restful", "api"],
    "restful": ["rest", "rest api", "api"],
    "graphql": ["api", "apollo", "relay"],
    
    # Java Stack
    "java": ["java 8", "java 11", "java 17", "spring", "spring boot", "spring mvc", "spring security", "hibernate", "jpa", "maven", "gradle"],
    "spring": ["spring framework", "spring boot", "spring mvc", "spring security", "spring data", "spring cloud", "spring batch", "java"],
    "spring boot": ["springboot", "spring boot 2", "spring boot 3", "spring", "java"],
    "springboot": ["spring boot", "spring"],
    "hibernate": ["hibernate", "jpa", "java persistence api", "orm", "java"],
    "jpa": ["java persistence api", "hibernate", "orm", "java"],
    
    # PHP Stack
    "php": ["php 7", "php 8", "laravel", "symfony", "codeigniter", "zend", "yii", "cakephp"],
    "laravel": ["laravel framework", "eloquent orm", "blade", "artisan", "php"],
    "symfony": ["symfony framework", "doctrine", "twig", "php"],
    
    # Databases
    "sql": ["mysql", "postgresql", "sql server", "oracle", "sqlite", "t-sql", "pl/sql"],
    "postgresql": ["postgres", "postgresql", "pgsql"],
    "postgres": ["postgresql", "pgsql"],
    "mongodb": ["mongo", "nosql"],
    "mongo": ["mongodb", "nosql"],
    "mysql": ["mariadb", "percona", "sql"],
    "redis": ["redis cache", "redis cluster", "cache"],
    "elasticsearch": ["elastic search", "elk stack", "logstash", "kibana"],
}

# Database type categorization for matching databases of the same type
DATABASE_TYPES = {
    "relational": [
        "mysql", "mariadb", "percona", "postgresql", "postgres", "pgsql",
        "sql server", "mssql", "ms sql", "microsoft sql server",
        "oracle", "sqlite", "sql", "t-sql", "pl/sql",
        "azure sql", "amazon rds", "rds", "aurora", "aurora mysql", "aurora postgresql",
        "cockroachdb", "cockroach", "yugabyte", "yugabytedb",
        "db2", "informix", "teradata", "snowflake", "bigquery", "redshift"
    ],
    "non-relational": [
        "mongodb", "mongo", "nosql", "cassandra", "couchdb", "dynamodb",
        "couchbase", "ravendb", "documentdb", "cosmos db", "azure cosmos db"
    ],
    "vector": [
        "pinecone", "weaviate", "qdrant", "milvus", "chroma", "chromadb",
        "pgvector", "postgresql vector", "vector database", "vector db",
        "faiss", "annoy", "nmslib", "hnswlib"
    ],
    "key-value": [
        "redis", "redis cache", "redis cluster", "memcached", "hazelcast",
        "riak", "aerospike", "etcd", "consul"
    ],
    "graph": [
        "neo4j", "arangodb", "orientdb", "amazon neptune", "neptune",
        "azure cosmos db graph", "janusgraph", "dgraph"
    ],
    "time-series": [
        "influxdb", "timescaledb", "timescale", "prometheus", "opentsdb",
        "kdb+", "questdb", "victoriametrics"
    ],
    "search": [
        "elasticsearch", "elastic search", "solr", "apache solr",
        "opensearch", "algolia", "meilisearch", "typesense"
    ]
}

def get_database_type(db_name: str) -> Optional[str]:
    """
    Get the database type category for a given database name.
    Returns: "relational", "non-relational", "vector", "key-value", "graph", "time-series", "search", or None
    """
    if not db_name:
        return None
    db_lower = db_name.lower().strip()
    
    for db_type, databases in DATABASE_TYPES.items():
        if db_lower in databases:
            return db_type
        # Also check if db_name contains any of the database names
        for db in databases:
            if db in db_lower or db_lower in db:
                return db_type
    
    return None

def databases_same_type(db1: str, db2: str) -> bool:
    """
    Check if two databases are of the same type (e.g., both relational).
    Returns True if they're the same type, False otherwise.
    """
    if not db1 or not db2:
        return False
    
    type1 = get_database_type(db1)
    type2 = get_database_type(db2)
    
    if type1 and type2:
        return type1 == type2
    
    return False


def get_all_match_terms(keyword: str) -> set:
    """Return keyword + all equivalents/related terms (lowercase) for matching."""
    k = keyword.lower().strip()
    if not k:
        return set()
    out = {k}
    for canonical, variants in SKILL_EQUIVALENCES.items():
        if k == canonical or k in variants:
            out.add(canonical)
            out.update(variants)
            break
    return out


def skill_matches_keyword(skill_lower: str, keyword_lower: str) -> bool:
    """
    True if candidate skill matches job keyword (direct, equivalence, substring, or same database type).
    E.g. job "Node.js" matches skill "JavaScript"; job "JavaScript" matches skill "Node.js".
    E.g. job "MS SQL" matches skill "MySQL" (both relational databases).
    """
    if not skill_lower or not keyword_lower:
        return False
    if skill_lower == keyword_lower:
        return True
    # Keyword's match set: what skills satisfy this job keyword
    kw_match = get_all_match_terms(keyword_lower)
    if skill_lower in kw_match:
        return True
    # Also check: skill's match set (e.g. skill "javascript" → variants include "node.js")
    skill_match = get_all_match_terms(skill_lower)
    if keyword_lower in skill_match:
        return True
    # Database type matching: if both are databases of the same type, they match
    if databases_same_type(skill_lower, keyword_lower):
        return True
    # Substring match
    if keyword_lower in skill_lower or skill_lower in keyword_lower:
        return True
    return False


def is_exact_match(skill_lower: str, keyword_lower: str) -> bool:
    """
    Check if skill exactly matches keyword (not related/equivalent).
    Returns True only for exact matches, False for related matches.
    
    Exact match means:
    - Identical strings (case-insensitive)
    - One is a substring of the other (e.g., "react" in "react.js")
    - But NOT related through skill equivalences (e.g., "C#" vs ".NET" is NOT exact)
    """
    if not skill_lower or not keyword_lower:
        return False
    
    # Exact match (case-insensitive)
    if skill_lower == keyword_lower:
        return True
    
    # First check if they're related through equivalences
    # If they are, it's NOT an exact match (even if one is substring of other)
    kw_match = get_all_match_terms(keyword_lower)
    skill_match = get_all_match_terms(skill_lower)
    
    # If skill is in keyword's equivalence set (but not identical), it's related, not exact
    if skill_lower in kw_match and skill_lower != keyword_lower:
        return False
    # If keyword is in skill's equivalence set (but not identical), it's related, not exact
    if keyword_lower in skill_match and skill_lower != keyword_lower:
        return False
    
    # If not related through equivalences, check substring match
    # (e.g., "react" in "react.js" or "react.js" contains "react")
    if keyword_lower in skill_lower or skill_lower in keyword_lower:
        return True
    
    return False


def is_related_match(skill_lower: str, keyword_lower: str) -> bool:
    """
    Check if skill is related/equivalent to keyword but not exact.
    Returns True for related matches, False for exact or no match.
    Includes database type matching (e.g., MS SQL and MySQL are related as both relational).
    """
    if not skill_lower or not keyword_lower:
        return False
    # If it's an exact match, it's not a related match
    if is_exact_match(skill_lower, keyword_lower):
        return False
    # Check if they're related through equivalences
    kw_match = get_all_match_terms(keyword_lower)
    if skill_lower in kw_match:
        return True
    skill_match = get_all_match_terms(skill_lower)
    if keyword_lower in skill_match:
        return True
    # Database type matching: if both are databases of the same type (but not exact), they're related
    if databases_same_type(skill_lower, keyword_lower):
        return True
    return False
