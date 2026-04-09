import logging
from asyncio import Queue, Lock, Event
from typing import Dict, Any, List, Set


def get_logger() -> logging.Logger:
    from server import logger
    return logger


def get_log_ws_manager():
    from server import log_ws_manager
    return log_ws_manager


def get_request_queue() -> Queue:
    from server import request_queue
    return request_queue


def get_processing_lock() -> Lock:
    from server import processing_lock
    return processing_lock


def get_worker_task():
    from server import worker_task
    return worker_task


def get_server_state() -> Dict[str, Any]:
    from server import is_initializing, is_playwright_ready, is_browser_connected, is_page_ready, browser_instance
    
    # Check if browser is still actually connected if it was supposed to be
    actual_browser_connected = is_browser_connected
    actual_page_ready = is_page_ready
    
    if is_browser_connected and browser_instance:
        if not browser_instance.is_connected():
            actual_browser_connected = False
            actual_page_ready = False
            # Update the global state in server module as well
            import server
            server.is_browser_connected = False
            server.is_page_ready = False
            server.logger.error("检测到浏览器连接已断开，已更新状态。")

    return {
        'is_initializing': is_initializing,
        'is_playwright_ready': is_playwright_ready,
        'is_browser_connected': actual_browser_connected,
        'is_page_ready': actual_page_ready
    }


def get_page_instance():
    from server import page_instance
    return page_instance


def get_model_list_fetch_event() -> Event:
    from server import model_list_fetch_event
    return model_list_fetch_event


def get_parsed_model_list() -> List[Dict[str, Any]]:
    from server import parsed_model_list
    return parsed_model_list


def get_excluded_model_ids() -> Set[str]:
    from server import excluded_model_ids
    return excluded_model_ids


def get_current_ai_studio_model_id() -> str:
    from server import current_ai_studio_model_id
    return current_ai_studio_model_id