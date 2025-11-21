# -*- coding: utf-8 -*-
"""
Simple network handler using the requests library.
Much simpler than QgsBlockingNetworkRequest and respects system proxy settings.
"""

import json
import requests
from typing import Dict, Any, Optional
from .logging import logger


class SimpleNetworkHandler:
    """
    Simple network handler using requests library.
    Automatically respects system proxy settings and is much easier to use.
    """
    
    def __init__(self, timeout: int = 30):
        """
        Initialize the network handler.
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        
    def post_json(self, url: str, headers: Dict[str, str], data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform a POST request with JSON data.
        
        Args:
            url: The URL to send the request to
            headers: HTTP headers to include
            data: JSON data to send in the request body
            
        Returns:
            Dictionary containing response data and metadata
        """
        try:
            logger.info(f"Making request to: {url}")
            
            # Make the request - requests automatically handles proxy settings
            response = requests.post(
                url=url,
                headers=headers,
                json=data,  # requests automatically handles JSON encoding
                timeout=self.timeout
            )
            
            # Check if the request was successful
            response.raise_for_status()
            
            logger.info(f"Received response with status {response.status_code}")
            
            return {
                'success': True,
                'data': response.json(),
                'status_code': response.status_code,
                'headers': dict(response.headers)
            }
            
        except requests.exceptions.Timeout:
            error_msg = f"Request timed out after {self.timeout} seconds"
            logger.error(error_msg)
            logger.error(f"Full request - URL: {url}, Headers: {headers}, Data: {json.dumps(data)}")
            return {
                'success': False,
                'error': error_msg,
                'status_code': None
            }
            
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Connection error: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Full request - URL: {url}, Headers: {headers}, Data: {json.dumps(data)}")
            return {
                'success': False,
                'error': error_msg,
                'status_code': None
            }
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP error {response.status_code}: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Full request - URL: {url}, Headers: {headers}, Data: {json.dumps(data)}")
            return {
                'success': False,
                'error': error_msg,
                'status_code': response.status_code
            }
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Full request - URL: {url}, Headers: {headers}, Data: {json.dumps(data)}")
            return {
                'success': False,
                'error': error_msg,
                'status_code': None
            }
            
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON response: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Full request - URL: {url}, Headers: {headers}, Data: {json.dumps(data)}")
            return {
                'success': False,
                'error': error_msg,
                'status_code': response.status_code,
                'raw_content': response.text
            }


class NetworkError(Exception):
    """Custom exception for network-related errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class TimeoutError(NetworkError):
    """Custom exception for network timeout errors."""
    pass
