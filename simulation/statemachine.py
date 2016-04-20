from processor import CanProcess


class StateMachineException(Exception):
    pass


class StateMachine(CanProcess, object):
    def __init__(self, target, cfg):
        """
        Cycle based state machine.

        :param target: Reference to object instance which implements state handlers.
        :param cfg: dict which contains state machine configuration.

        The configuration should contain the following keys:
        - initial: Name of the initial state of this machine
        - transitions: List of transitions in this state machine.

        Transitions should be provided as tuples with three elements:
        - From State: String name of state that this transition leaves
        - To State: String name of state that this transition enters
        - Condition Function: Condition under which the transition should be executed

        The condition function may be a function reference, a lambda, or a string name.

        If a name is provided, it will resolve to calling target._check_[name]().

        A condition function should take no arguments and return True or False. If True
        is returned, the transition will be executed.

        Only one transition may occur per cycle. Every cycle will, at the very least,
        trigger a in_state event against the current state. See process() for details.
        """
        super(StateMachine, self).__init__()

        self._target = None
        self._initial = None
        self._state = None

        self._handler = {}  # Nested dict mapping [state][event] = handler
        self._transition = {}  # Nested dict mapping [from_state][to_state] = transition
        self._prefix = {  # Default prefixes used when calling handler/transition functions by name
                          'on_entry': '_on_entry_',
                          'in_state': '_in_state_',
                          'on_exit': '_on_exit_',
                          'transition': '_check_'
                          }

        # The None state represents the condition when the machine has not yet entered
        # the initial state. This will be the case before the first cycle and immediately
        # following a reset(). It has no name and no handlers.
        self._add_state(None, None, None, None)

        # Apply initial config
        self.target = target
        self.extend(cfg)

    @property
    def state(self):
        return self._state

    @property
    def target(self):
        return self._target

    @target.setter
    def target(self, value):
        self._target = value

    def extend(self, cfg):
        """
        Extend the current configuration of this state machine.

        Overwrites previous settings and adds new ones.

        :param cfg: dict containing configuration amendments. See __init__ for details.
        """
        if 'initial' in cfg:
            self._initial = cfg['initial']

        # TODO: Allow user to explicitly specify states and their handlers?

        for from_state, to_state, check_func in cfg.get('transitions', []):
            if from_state not in self._handler:
                self._add_state(from_state)
            if to_state not in self._handler:
                self._add_state(to_state)
            self._add_transition(from_state, to_state, check_func)

            # TODO: Allow user to override handler prefix settings?

    def doProcess(self, dt):
        """
        Process a cycle of this state machine.

        A cycle will perform at most one transition. A transition will only occur if one
        of the transition check functions leaving the current state returns True.

        When a transition occurs, the following events are raised:
         - on_exit_old_state()
         - on_entry_new_state()
         - in_state_new_state()

        The first cycle after init or reset will never call transition checks and, instead,
        always performs on_entry and in_state on the initial state.

        Whether a transition occurs or not, and regardless of any other circumstances, a
        cycle always ends by raising an in_state event on the current (potentially new)
        state.

        :param dt: Delta T. "Time" passed since last cycle, passed on to event handlers.
        """
        # Initial transition on first cycle / after a reset()
        if self._state is None:
            self._state = self._initial
            self._raise_event('on_entry', 0)
            self._raise_event('in_state', 0)
            return

        # General transition
        for target_state, check_func in self._transition[self._state].iteritems():
            if self._check_transition(check_func):
                self._raise_event('on_exit', dt)
                self._state = target_state
                self._raise_event('on_entry', dt)
                break

        # Always end with an in_state
        self._raise_event('in_state', dt)

    def reset(self):
        """
        Reset the state machine to before the first cycle. The next process() will enter the initial state.
        """
        self._state = None

    def _add_state(self, state, *args, **kwargs):
        """
        Add or update a state and its handlers.

        :param state: Name of state to be added or updated
        :param on_entry: Handler for on_entry events. May be function ref, string name or None.
        :param in_state: Handler for in_state events. May be function ref, string name or None.
        :param on_exit: Handler for on_exit events. May be function ref, string name or None.

        Handlers should take exactly one parameter (not counting self), delta T since last cycle, and return nothing.

        Handlers default to calling [target].[event_prefix][state_name](dt) if such a function exists on target.

        When explicitly set to None, no event will be raised at all.
        """
        # Variable arguments for state handlers
        # Default to calling target.on_entry_state_name(), etc
        on_entry = args[0] if len(args) > 0 else kwargs.get('on_entry', self._prefix['on_entry'] + state)
        in_state = args[1] if len(args) > 1 else kwargs.get('in_state', self._prefix['in_state'] + state)
        on_exit = args[2] if len(args) > 2 else kwargs.get('on_exit', self._prefix['on_exit'] + state)

        self._handler[state] = {'on_entry': on_entry,
                                'in_state': in_state,
                                'on_exit': on_exit}

    def _add_transition(self, from_state, to_state, transition_check):
        """
        Add or update a transition and its condition function.

        :param from_state: Name of state this transition leaves
        :param to_state: Name of state this transition enters
        :param transition_check: Condition under which this transition occurs. May be function ref or string name.

        The transition_check function should return True if the transition should occur. Otherwise, False.

        Transition condition functions should take no parameters (not counting self).
        """
        if from_state not in self._transition.keys():
            self._transition[from_state] = {}

        if not callable(transition_check):
            transition_check = self._prefix['transition'] + transition_check

        self._transition[from_state][to_state] = transition_check

    def _raise_event(self, event, dt):
        """
        Invoke the given event name for the current state, passing dt as a parameter.

        :param event: Name of event to raise on current state.
        :param dt: Delta T since last cycle.
        """
        # May be None, function reference, or string of target member function name
        handler = self._handler[self._state][event]

        if handler and not callable(handler):
            handler = getattr(self._target, handler, None)

        if handler and callable(handler):
            handler(dt)

    def _check_transition(self, check_func):
        """
        Check whether a transition should occur.

        :param check_func: Function reference or string name of target member function.
        :return: True of the transition should occur; False otherwise.
        """
        if not callable(check_func):
            check_func = getattr(self._target, check_func)

        return check_func()
