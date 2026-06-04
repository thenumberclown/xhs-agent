"""Tests for the database layer."""

from src.storage.database import Database


class TestDatabase:
    """CRUD tests for database operations."""

    def test_create_and_get_task(self, temp_db_path):
        db = Database(temp_db_path)
        db.init()

        task_id = db.create_task({
            "product_name": "测试产品",
            "product_desc": "这是一个测试产品描述",
            "platform": "xiaohongshu",
        })
        assert task_id > 0

        task = db.get_task(task_id)
        assert task is not None
        assert task["product_name"] == "测试产品"
        assert task["status"] == "draft"

    def test_save_and_get_copy(self, temp_db_path):
        db = Database(temp_db_path)
        db.init()

        task_id = db.create_task({
            "product_name": "测试产品",
            "product_desc": "测试",
        })

        copy_id = db.save_copy({
            "task_id": task_id,
            "version": 1,
            "title": "测试标题",
            "body": "测试正文内容",
            "hashtags": ["测试", "标签"],
        })
        assert copy_id > 0

        copy = db.get_copy(copy_id)
        assert copy is not None
        assert copy["title"] == "测试标题"
        assert len(copy["hashtags"]) == 2

    def test_save_reference(self, temp_db_path):
        db = Database(temp_db_path)
        db.init()

        ref_id = db.save_reference({
            "title": "参考标题",
            "body": "参考正文",
            "likes": 1000,
            "quality_label": "success",
        })
        assert ref_id > 0

        refs = db.list_references(quality_label="success")
        assert len(refs) >= 1
        assert refs[0]["title"] == "参考标题"

    def test_list_tasks(self, temp_db_path):
        db = Database(temp_db_path)
        db.init()

        db.create_task({"product_name": "产品A", "product_desc": "描述A"})
        db.create_task({"product_name": "产品B", "product_desc": "描述B",
                        "platform": "douyin"})

        all_tasks = db.list_tasks()
        assert len(all_tasks) == 2

        xhs_tasks = db.list_tasks(platform="xiaohongshu")
        assert len(xhs_tasks) == 1

    def test_update_task_status(self, temp_db_path):
        db = Database(temp_db_path)
        db.init()

        task_id = db.create_task({"product_name": "产品", "product_desc": "描述"})
        db.update_task_status(task_id, "published")

        task = db.get_task(task_id)
        assert task["status"] == "published"

    def test_save_performance(self, temp_db_path):
        db = Database(temp_db_path)
        db.init()

        task_id = db.create_task({"product_name": "产品", "product_desc": "描述"})
        copy_id = db.save_copy({
            "task_id": task_id,
            "title": "标题",
            "body": "正文",
        })

        perf_id = db.save_performance({
            "copy_id": copy_id,
            "likes": 100,
            "collects": 50,
            "comments": 20,
            "shares": 10,
            "views": 2000,
        })
        assert perf_id > 0
        assert perf_id > 0
