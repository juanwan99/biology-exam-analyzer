# Schema Contract — biology_edu

> Generated: 2026-03-24
> 热路径主入口: POST /api/analyze_auto

## 热路径必需表（13 张）

### exercise_bank (701 rows)
| column | type | nullable |
|--------|------|----------|
| id | integer | NO |
| source_id | integer | YES |
| question_type | character varying | NO |
| content | text | NO |
| content_embedding | USER-DEFINED | YES |
| options | jsonb | YES |
| answer | text | YES |
| explanation | text | YES |
| knowledge_point_ids | ARRAY | YES |
| chapter_ids | ARRAY | YES |
| difficulty_level | numeric | YES |
| competency_scores | jsonb | YES |
| tags | ARRAY | YES |
| usage_count | integer | YES |
| created_at | timestamp without time zone | YES |
| updated_at | timestamp without time zone | YES |

### exercise_sources (33 rows)
| column | type | nullable |
|--------|------|----------|
| id | integer | NO |
| name | character varying | NO |
| source_type | character varying | YES |
| year | integer | YES |
| region | character varying | YES |
| description | text | YES |
| created_at | timestamp without time zone | YES |

### knowledge_points (0 rows)
| column | type | nullable |
|--------|------|----------|
| id | integer | NO |
| chapter_id | integer | YES |
| name | character varying | NO |
| description | text | YES |
| description_embedding | USER-DEFINED | YES |
| difficulty_level | integer | YES |
| importance_level | integer | YES |
| competency_tags | jsonb | YES |
| prerequisite_ids | ARRAY | YES |
| keywords | ARRAY | YES |
| created_at | timestamp without time zone | YES |
| updated_at | timestamp without time zone | YES |

### textbook_pages (622 rows)
| column | type | nullable |
|--------|------|----------|
| id | integer | NO |
| book_id | character varying | NO |
| book_name | character varying | NO |
| page_num | integer | NO |
| markdown_content | text | YES |
| chapter_info | jsonb | YES |
| image_path | character varying | YES |
| created_at | timestamp without time zone | YES |

### textbook_chunks (1734 rows)
| column | type | nullable |
|--------|------|----------|
| id | integer | NO |
| page_id | integer | YES |
| book_id | character varying | NO |
| chunk_index | integer | NO |
| chunk_content | text | NO |
| page_num | integer | YES |
| chapter_info | jsonb | YES |
| embedding | USER-DEFINED | YES |
| created_at | timestamp without time zone | YES |

### textbook_versions (0 rows)
| column | type | nullable |
|--------|------|----------|
| id | integer | NO |
| name | character varying | NO |
| description | text | YES |
| created_at | timestamp without time zone | YES |

### admin_users (20 rows)
| column | type | nullable |
|--------|------|----------|
| id | integer | NO |
| username | character varying | NO |
| password_hash | character varying | NO |
| display_name | character varying | YES |
| role | character varying | YES |
| is_active | integer | YES |
| last_login | timestamp without time zone | YES |
| created_at | timestamp without time zone | YES |
| updated_at | timestamp without time zone | YES |

### operation_logs (16 rows)
| column | type | nullable |
|--------|------|----------|
| id | integer | NO |
| user_id | integer | YES |
| username | character varying | YES |
| operation | character varying | NO |
| target_type | character varying | NO |
| target_id | integer | YES |
| target_name | character varying | YES |
| old_value | jsonb | YES |
| new_value | jsonb | YES |
| ip_address | character varying | YES |
| created_at | timestamp without time zone | YES |

### resources (0 rows)
| column | type | nullable |
|--------|------|----------|
| id | integer | NO |
| resource_type | character varying | NO |
| title | character varying | YES |
| description | text | YES |
| file_path | character varying | YES |
| file_size | integer | YES |
| mime_type | character varying | YES |
| chapter_ids | ARRAY | YES |
| knowledge_point_ids | ARRAY | YES |
| tags | ARRAY | YES |
| extra_data | jsonb | YES |
| created_at | timestamp without time zone | YES |

### exam_history (0 rows)
| column | type | nullable |
|--------|------|----------|
| id | integer | NO |
| name | character varying | NO |
| exam_date | timestamp without time zone | YES |
| grade | character varying | NO |
| student_count | integer | YES |
| total_score | numeric | NO |
| average_score | numeric | YES |
| score_rate | numeric | YES |
| difficulty_avg | numeric | YES |
| source_file | character varying | YES |
| created_at | timestamp without time zone | YES |
| updated_at | timestamp without time zone | YES |

### question_performance (0 rows)
| column | type | nullable |
|--------|------|----------|
| id | integer | NO |
| exam_id | integer | YES |
| question_number | integer | NO |
| absolute_difficulty | numeric | YES |
| knowledge_complexity | numeric | YES |
| cognitive_level | numeric | YES |
| question_score | numeric | NO |
| actual_average | numeric | YES |
| score_rate | numeric | YES |
| knowledge_points | jsonb | YES |
| textbook_chapter | character varying | YES |
| question_type | character varying | YES |
| question_content | text | YES |
| created_at | timestamp without time zone | YES |

### difficulty_mapping (0 rows)
| column | type | nullable |
|--------|------|----------|
| id | integer | NO |
| mapping_type | character varying | NO |
| mapping_key | character varying | YES |
| grade | character varying | NO |
| difficulty_min | numeric | NO |
| difficulty_max | numeric | NO |
| avg_score_rate | numeric | YES |
| score_rate_stddev | numeric | YES |
| sample_count | integer | YES |
| confidence | numeric | YES |
| slope | numeric | YES |
| intercept | numeric | YES |
| updated_at | timestamp without time zone | YES |

### score_prediction (0 rows)
| column | type | nullable |
|--------|------|----------|
| id | integer | NO |
| exam_name | character varying | YES |
| grade | character varying | YES |
| total_score | numeric | YES |
| question_count | integer | YES |
| predicted_average | numeric | YES |
| predicted_rate | numeric | YES |
| confidence_lower | numeric | YES |
| confidence_upper | numeric | YES |
| reliability_score | numeric | YES |
| per_question_data | jsonb | YES |
| warnings | jsonb | YES |
| actual_average | numeric | YES |
| prediction_error | numeric | YES |
| created_at | timestamp without time zone | YES |
| updated_at | timestamp without time zone | YES |
