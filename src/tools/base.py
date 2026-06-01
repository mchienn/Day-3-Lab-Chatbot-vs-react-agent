import inspect
from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseTool(ABC):
    """
    Abstract Base Class representing a tool that can be used by an AI Agent.
    
    Subclasses must implement the name, description, and execute method.
    The execute method should always return its outputs as a string (plain text or JSON string).
    """

    def __init__(self, name: str, description: str):
        """
        Initialize the tool.

        Args:
            name: The name of the tool (used by the LLM).
            description: A detailed description of the tool and its arguments.
        """
        self.name = name
        self.description = description

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """
        Execute the tool's core logic with keyword arguments.

        Args:
            **kwargs: Arguments needed for execution.

        Returns:
            str: The output of the tool (plain text or JSON string).
        """
        pass

    def execute_from_string(self, args_str: str) -> str:
        """
        Adapts a raw string argument from the ReAct Agent, parses it,
        and invokes the tool's execute method.

        Args:
            args_str: The raw string of arguments from the ReAct loop.

        Returns:
            str: The execution result or an error message if parsing fails.
        """
        # Clean the argument string
        args_str = args_str.strip()

        # Get the signature of the execute method to inspect its parameters
        sig = inspect.signature(self.execute)
        # Exclude self and variable keyword/positional parameters (*args, **kwargs)
        params = [
            name for name, param in sig.parameters.items()
            if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        ]

        if not params:
            try:
                return self.execute()
            except Exception as e:
                return f"Error: Failed to execute tool '{self.name}'. Details: {str(e)}"

        kwargs = {}

        # If the execute method only takes one parameter, pass the entire string directly
        if len(params) == 1:
            kwargs[params[0]] = args_str.strip('\'"')
        else:
            # Parse multiple arguments separated by commas, stripping outer whitespace and quotes
            parts = [part.strip().strip('\'"') for part in args_str.split(',') if part.strip()]
            
            for i, param_name in enumerate(params):
                if i < len(parts):
                    kwargs[param_name] = parts[i]
                else:
                    # If missing a parameter, we pass None and let execute handle it or fail gracefully
                    kwargs[param_name] = None

        try:
            return self.execute(**kwargs)
        except Exception as e:
            return f"Error: Failed to execute tool '{self.name}'. Details: {str(e)}"

    def to_agent_dict(self) -> Dict[str, Any]:
        """
        Converts the tool instance into the dictionary structure expected by ReActAgent.

        Returns:
            Dict[str, Any]: A dictionary containing name, description, and callable function.
        """
        return {
            "name": self.name,
            "description": self.description,
            "function": self.execute_from_string
        }
