"""Every SQL statement the web app runs, in one place.

The point of the project is that these stay this short: the history lives in
the table definition (sql/schema.sql), not in the queries.
"""

LIST_ARTICLES = """
SELECT title FROM pages ORDER BY title
"""

# The article as it stood at a moment in time.
ARTICLE_AS_OF = """
SELECT c.rev_id, c.editor, c.edit_comment, c.content, c.sys_start, c.sys_end
FROM page_content FOR SYSTEM_TIME AS OF TIMESTAMP ? AS c
JOIN pages p USING (page_id)
WHERE p.title = ?
"""

# Every stored version of one article, for the timeline.
ARTICLE_VERSIONS = """
SELECT c.rev_id, c.editor, c.sys_start, LENGTH(c.content) AS bytes
FROM page_content FOR SYSTEM_TIME ALL AS c
JOIN pages p USING (page_id)
WHERE p.title = ?
ORDER BY c.sys_start
"""
