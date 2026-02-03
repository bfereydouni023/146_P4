import pyhop
import json

def check_enough(state, ID, item, num):
	if getattr(state,item)[ID] >= num: return []
	return False

def produce_enough(state, ID, item, num):
	if item == 'ingot':
		return [('produce_ingot', ID)] * num + [('have_enough', ID, item, num)]
	return [('produce', ID, item), ('have_enough', ID, item, num)]

pyhop.declare_methods('have_enough', check_enough, produce_enough)

def produce(state, ID, item):
	return [('produce_{}'.format(item), ID)]

pyhop.declare_methods('produce', produce)

def make_method(name, rule):
	def method(state, ID):
		# A method expands "produce_<item>" into the steps required by this recipe.
		# We don't check for resources here; we instead add "have_enough" subtasks
		# so the planner will figure out how to obtain them.
		subtasks = []
		for item, num in rule.get('Requires', {}).items():
			subtasks.append(('have_enough', ID, item, num))
		for item, num in rule.get('Consumes', {}).items():
			subtasks.append(('have_enough', ID, item, num))
		ingot_tasks = [task for task in subtasks if task[2] == 'ingot']
		other_tasks = [task for task in subtasks if task[2] != 'ingot']
		subtasks = other_tasks + ingot_tasks
		subtasks.append(('op_{}'.format(name.replace(' ', '_')), ID))
		return subtasks

	method._recipe_time = rule.get('Time', 0)
	return method

def declare_methods(data):
	# some recipes are faster than others for the same product even though they might require extra tools
	# sort the recipes so that faster recipes go first

	recipe_order = {}
	for recipe_name, rule in data['Recipes'].items():
		for product in rule['Produces'].keys():
			recipe_order.setdefault(product, []).append((recipe_name, rule))

	for product, recipes in recipe_order.items():
		recipes.sort(key=lambda recipe: recipe[1]['Time'])
		methods = []
		for recipe_name, rule in recipes:
			method = make_method(recipe_name, rule)
			# Give the method a descriptive name for debugging/printing clarity.
			method.__name__ = 'method_{}'.format(recipe_name.replace(' ', '_'))
			methods.append(method)
		pyhop.declare_methods('produce_{}'.format(product), *methods)
	# hint: call make_method, then declare the method to pyhop using pyhop.declare_methods('foo', m1, m2, ..., mk)	
					

def make_operator(name, rule):
	def operator(state, ID):
		# Operators are the primitive actions that mutate the state.
		if state.time[ID] < rule['Time']:
			return False
		for item, num in rule.get('Requires', {}).items():
			if getattr(state, item)[ID] < num:
				return False
		for item, num in rule.get('Consumes', {}).items():
			if getattr(state, item)[ID] < num:
				return False
		state.time[ID] -= rule['Time']
		for item, num in rule.get('Consumes', {}).items():
			getattr(state, item)[ID] -= num
		for item, num in rule.get('Produces', {}).items():
			getattr(state, item)[ID] += num
			if item in data.get('Tools', []):
				state.made_tools[ID].add(item)
		return state
	operator.__name__ = 'op_{}'.format(name.replace(' ', '_'))
	return operator

def declare_operators(data):
	operators = []
	for recipe_name, rule in data['Recipes'].items():
		operators.append(make_operator(recipe_name, rule))
	pyhop.declare_operators(*operators)
	# hint: call make_operator, then declare the operator to pyhop using pyhop.declare_operators(o1, o2, ..., ok)

def add_heuristic(data, ID):
	# prune search branch if heuristic() returns True
	# do not change parameters to heuristic(), but can add more heuristic functions with the same parameters: 
	# e.g. def heuristic2(...); pyhop.add_check(heuristic2)
	producible = set()
	for rule in data['Recipes'].values():
		producible.update(rule['Produces'].keys())
	tools = set(data.get('Tools', []))
	goal_items = set(data.get('Problem', {}).get('Goal', {}).keys())
	disallowed_tools = {
		tool for tool in tools
		if tool not in goal_items and (tool.startswith('iron_') or tool.endswith('_axe'))
	}
	min_unit_time = {}
	for rule in data['Recipes'].values():
		if any(item in disallowed_tools for item in rule.get('Requires', {}).keys()):
			continue
		rule_time = rule['Time']
		for product, qty in rule['Produces'].items():
			unit_time = rule_time / qty
			current = min_unit_time.get(product)
			if current is None or unit_time < current:
				min_unit_time[product] = unit_time
	inventory_keys = list(data.get('Items', [])) + list(data.get('Tools', []))
	best_time = {}
	axes = {tool for tool in tools if tool.endswith('_axe')}

	def heuristic(state, curr_task, tasks, plan, depth, calling_stack):
		# If time goes negative, the plan is invalid.
		if state.time[ID] < 0:
			return True
		state_key = (curr_task, tuple(tasks), tuple(getattr(state, item)[ID] for item in inventory_keys))
		remaining_time = state.time[ID]
		previous_best = best_time.get(state_key)
		if previous_best is not None and remaining_time <= previous_best:
			return True
		best_time[state_key] = remaining_time
		if isinstance(curr_task, tuple):
			task_name = curr_task[0]
			if task_name == 'produce':
				item = curr_task[2]
				if curr_task in calling_stack and item in tools:
					return True
			elif task_name == 'have_enough':
				item = curr_task[2]
				required = curr_task[3]
				# If we need more of an item and no recipe can produce it, prune.
				if getattr(state, item)[ID] < required and item not in producible:
					return True
				if item in disallowed_tools and getattr(state, item)[ID] < required:
					return True
			elif task_name == 'produce':
				item = curr_task[2]
				# Tools aren't consumed; avoid crafting duplicates.
				if item in tools and getattr(state, item)[ID] >= 1:
					return True
				if item in tools and item in state.made_tools[ID]:
					return True
				if item in tools and item.startswith('iron_') and item not in goal_items:
					return True
				if item in tools and item.endswith('_axe') and item not in goal_items:
					return True
			elif task_name.startswith('produce_'):
				item = task_name.replace('produce_', '', 1)
				if curr_task in calling_stack and item in tools:
					return True
				if item in tools and getattr(state, item)[ID] >= 1:
					return True
				if item in tools and item in state.made_tools[ID]:
					return True
				if item in tools and item.startswith('iron_') and item not in goal_items:
					return True
				if item in tools and item.endswith('_axe') and item not in goal_items:
					return True
				if item in axes:
					wood_needed = 0
					for task in (curr_task,) + tuple(tasks):
						if not isinstance(task, tuple):
							continue
						if task[0] == 'have_enough' and task[2] == 'wood':
							wood_needed = max(wood_needed, task[3] - getattr(state, 'wood')[ID])
						elif task[0] == 'produce_wood':
							wood_needed = max(wood_needed, 1 - getattr(state, 'wood')[ID])
					if wood_needed <= 0 and 'wood' not in goal_items:
						return True
		estimated_time = 0.0
		for task in (curr_task,) + tuple(tasks):
			if not isinstance(task, tuple):
				continue
			task_name = task[0]
			if task_name == 'have_enough':
				item = task[2]
				required = task[3]
				if item in min_unit_time:
					deficit = max(0, required - getattr(state, item)[ID])
					estimated_time += deficit * min_unit_time[item]
			elif task_name == 'produce':
				item = task[2]
				if item in min_unit_time:
					estimated_time += min_unit_time[item]
			elif task_name.startswith('produce_'):
				item = task_name.replace('produce_', '', 1)
				if item in min_unit_time:
					estimated_time += min_unit_time[item]
		if estimated_time > state.time[ID]:
			return True
		return False # if True, prune this branch

	pyhop.add_check(heuristic)

def define_ordering(data, ID):
	# if needed, use the function below to return a different ordering for the methods
	# note that this should always return the same methods, in a new order, and should not add/remove any new ones
	tools = set(data.get('Tools', []))
	goal_items = set(data.get('Problem', {}).get('Goal', {}).keys())
	disallowed_tools = {
		tool for tool in tools
		if tool not in goal_items and (tool.startswith('iron_') or tool.endswith('_axe'))
	}
	min_unit_time = {}
	for rule in data['Recipes'].values():
		if any(item in disallowed_tools for item in rule.get('Requires', {}).keys()):
			continue
		rule_time = rule['Time']
		for product, qty in rule['Produces'].items():
			unit_time = rule_time / qty
			current = min_unit_time.get(product)
			if current is None or unit_time < current:
				min_unit_time[product] = unit_time
	tool_tiers = {
		'wooden': 1,
		'stone': 2,
		'iron': 3,
	}

	def reorder_methods(state, curr_task, tasks, plan, depth, calling_stack, methods):
		scored_methods = []
		target_item = None
		if isinstance(curr_task, tuple) and curr_task[0].startswith('produce_'):
			target_item = curr_task[0].replace('produce_', '', 1)
		preferred_tool = None
		if target_item == 'cobble':
			if getattr(state, 'stone_pickaxe')[ID] > 0:
				preferred_tool = 'stone_pickaxe'
			elif getattr(state, 'wooden_pickaxe')[ID] > 0:
				preferred_tool = 'wooden_pickaxe'
			else:
				preferred_tool = 'wooden_pickaxe'
		elif target_item in {'coal', 'ore'}:
			if getattr(state, 'iron_pickaxe')[ID] > 0:
				preferred_tool = 'iron_pickaxe'
			elif getattr(state, 'stone_pickaxe')[ID] > 0:
				preferred_tool = 'stone_pickaxe'
			else:
				preferred_tool = 'stone_pickaxe'
		for method in methods:
			subtasks = pyhop.get_subtasks(method, state, curr_task)
			missing_tools = 0
			missing_items = 0
			required_tool_tier = 0
			recipe_time = getattr(method, '_recipe_time', 0)
			requires_stone_pickaxe = False
			estimated_time = 0.0
			method_tool = None
			for subtask in subtasks:
				if subtask[0] != 'have_enough':
					continue
				item = subtask[2]
				required = subtask[3]
				available = getattr(state, item)[ID]
				if available < required:
					if item in tools:
						missing_tools += 1
					else:
						missing_items += 1
					if item in min_unit_time:
						estimated_time += (required - available) * min_unit_time[item]
				if item in tools:
					tier_name = item.split('_', 1)[0]
					required_tool_tier = max(required_tool_tier, tool_tiers.get(tier_name, 4))
					if method_tool is None:
						method_tool = item
				if item == 'stone_pickaxe':
					requires_stone_pickaxe = True
			if preferred_tool is None:
				prefer_flag = 0 if method_tool is None else 1
			else:
				prefer_flag = 0 if method_tool == preferred_tool else 1
			if missing_tools == 0:
				score = (prefer_flag, missing_items, estimated_time, recipe_time, len(subtasks))
			else:
				score = (prefer_flag, missing_tools, required_tool_tier, missing_items, estimated_time, recipe_time, len(subtasks))
			scored_methods.append((score, method))
		scored_methods.sort(key=lambda entry: entry[0])
		return [method for _, method in scored_methods]
	
	pyhop.define_ordering(reorder_methods)

def set_up_state(data, ID):
	state = pyhop.State('state')
	setattr(state, 'time', {ID: data['Problem']['Time']})
	setattr(state, 'made_tools', {ID: set()})

	for item in data['Items']:
		setattr(state, item, {ID: 0})

	for item in data['Tools']:
		setattr(state, item, {ID: 0})

	for item, num in data['Problem']['Initial'].items():
		setattr(state, item, {ID: num})

	return state

def set_up_goals(data, ID):
	goals = []
	for item, num in data['Problem']['Goal'].items():
		goals.append(('have_enough', ID, item, num))

	return goals

if __name__ == '__main__':
	import sys
	rules_filename = 'crafting.json'
	if len(sys.argv) > 1:
		rules_filename = sys.argv[1]

	with open(rules_filename) as f:
		data = json.load(f)

	state = set_up_state(data, 'agent')
	goals = set_up_goals(data, 'agent')

	declare_operators(data)
	declare_methods(data)
	add_heuristic(data, 'agent')
	define_ordering(data, 'agent')

	# pyhop.print_operators()
	# pyhop.print_methods()

	# Hint: verbose output can take a long time even if the solution is correct; 
	# try verbose=1 if it is taking too long
	pyhop.pyhop(state, goals, verbose=1)
	# pyhop.pyhop(state, [('have_enough', 'agent', 'cart', 1),('have_enough', 'agent', 'rail', 20)], verbose=3)
