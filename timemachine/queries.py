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

# The same table read at two moments and joined to itself: the diff page.
# LEFT JOINs, so an article that did not exist yet at the first moment still
# comes back (with NULLs on that side).
ARTICLE_AT_TWO_MOMENTS = """
SELECT old.rev_id  AS old_rev_id,  old.sys_start AS old_start, old.content AS old_content,
       new.rev_id  AS new_rev_id,  new.sys_start AS new_start, new.content AS new_content
FROM pages p
LEFT JOIN page_content FOR SYSTEM_TIME AS OF TIMESTAMP ? AS old ON old.page_id = p.page_id
LEFT JOIN page_content FOR SYSTEM_TIME AS OF TIMESTAMP ? AS new ON new.page_id = p.page_id
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
