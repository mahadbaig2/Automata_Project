# fsm.py - Complete Finite State Machine for Task Reminder Bot

class TaskReminderFSM:
    """
    Finite State Machine to track task lifecycle

    States:
    - Idle: Initial state
    - Task Added: Task created by user
    - Priority Assigned: System assigns priority automatically
    - Pending: Task waiting for reminder time
    - Reminder Sent: Notification triggered
    - Task Completed: User marked task as done
    - Task Overdue: Deadline passed without completion
    - Task Repeated: Recurring task created new instance
    - Task Deleted: User removed task
    """

    def __init__(self):
        self.state = "Idle"
        self.state_history = ["Idle"]
        self.valid_transitions = {
            "Idle": ["add_task"],
            "Task Added": ["assign_priority", "delete_task"],
            "Priority Assigned": ["set_pending", "delete_task"],
            "Pending": ["trigger_reminder", "complete_task", "delete_task", "edit_task", "mark_overdue"],
            "Reminder Sent": ["complete_task", "repeat_task", "delete_task", "mark_overdue"],
            "Task Completed": ["repeat_task"],
            "Task Overdue": ["complete_task", "repeat_task", "delete_task"],
            "Task Repeated": ["set_pending"],
            "Task Deleted": []
        }
        print(f"[FSM] Initialized in state: {self.state}")

    def transition(self, event, task_info=""):
        """
        Transition to new state based on event

        Args:
            event: The event triggering transition
            task_info: Optional task description for logging
        """
        current_state = self.state
        new_state = None

        # Check if transition is valid
        if event not in self.valid_transitions.get(self.state, []):
            print(f"[FSM] ⚠️ Invalid transition: {event} from state '{self.state}'")
            return False

        # Define state transitions
        if self.state == "Idle" and event == "add_task":
            new_state = "Task Added"

        elif self.state == "Task Added" and event == "assign_priority":
            new_state = "Priority Assigned"

        elif self.state == "Priority Assigned" and event == "set_pending":
            new_state = "Pending"

        elif self.state == "Pending" and event == "trigger_reminder":
            new_state = "Reminder Sent"

        elif self.state in ["Pending", "Reminder Sent"] and event == "mark_overdue":
            new_state = "Task Overdue"

        elif self.state in ["Pending", "Reminder Sent", "Task Overdue"] and event == "complete_task":
            new_state = "Task Completed"

        elif self.state in ["Task Completed", "Reminder Sent", "Task Overdue"] and event == "repeat_task":
            new_state = "Task Repeated"

        elif self.state == "Task Repeated" and event == "set_pending":
            new_state = "Pending"

        elif event == "delete_task":
            new_state = "Task Deleted"

        elif self.state == "Pending" and event == "edit_task":
            new_state = "Priority Assigned"  # Re-evaluate priority after edit

        # Perform transition
        if new_state:
            self.state = new_state
            self.state_history.append(new_state)
            task_str = f" [{task_info}]" if task_info else ""
            print(f"[FSM] ✅ {current_state} --({event})--> {new_state}{task_str}")
            return True
        else:
            print(f"[FSM] ❌ No transition defined for '{event}' from '{self.state}'")
            return False

    def get_state(self):
        """Return current state"""
        return self.state

    def get_history(self):
        """Return state transition history"""
        return self.state_history

    def reset(self):
        """Reset FSM to initial state"""
        self.state = "Idle"
        self.state_history = ["Idle"]
        print("[FSM] 🔄 Reset to Idle state")

    def can_transition(self, event):
        """Check if a transition is valid without performing it"""
        return event in self.valid_transitions.get(self.state, [])

    def get_valid_transitions(self):
        """Get list of valid transitions from current state"""
        return self.valid_transitions.get(self.state, [])


# Example usage and testing
if __name__ == "__main__":
    print("=" * 60)
    print("Testing Task Reminder FSM")
    print("=" * 60)

    fsm = TaskReminderFSM()

    # Test Case 1: Normal task flow
    print("\n--- Test Case 1: Normal Task Flow ---")
    fsm.transition("add_task", "Submit assignment")
    fsm.transition("assign_priority")
    fsm.transition("set_pending")
    fsm.transition("trigger_reminder")
    fsm.transition("complete_task")

    # Test Case 2: Recurring task flow
    print("\n--- Test Case 2: Recurring Task Flow ---")
    fsm.reset()
    fsm.transition("add_task", "Daily standup meeting")
    fsm.transition("assign_priority")
    fsm.transition("set_pending")
    fsm.transition("trigger_reminder")
    fsm.transition("repeat_task")
    fsm.transition("set_pending")
    fsm.transition("trigger_reminder")
    fsm.transition("complete_task")

    # Test Case 3: Task deletion
    print("\n--- Test Case 3: Task Deletion ---")
    fsm.reset()
    fsm.transition("add_task", "Cancelled meeting")
    fsm.transition("assign_priority")
    fsm.transition("delete_task")

    # Test Case 4: Invalid transition
    print("\n--- Test Case 4: Invalid Transition ---")
    fsm.reset()
    fsm.transition("trigger_reminder")  # Can't trigger reminder from Idle

    # Test Case 5: Task editing
    print("\n--- Test Case 5: Task Edit Flow ---")
    fsm.reset()
    fsm.transition("add_task", "Project deadline")
    fsm.transition("assign_priority")
    fsm.transition("set_pending")
    fsm.transition("edit_task")
    fsm.transition("set_pending")

    print("\n--- Final State History ---")
    print(f"History: {' -> '.join(fsm.get_history())}")
    print(f"Current State: {fsm.get_state()}")
    print(f"Valid next transitions: {fsm.get_valid_transitions()}")