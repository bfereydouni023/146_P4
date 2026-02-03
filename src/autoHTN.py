import pyhop
import json

def check_enough(state, ID, item, num):
	if getattr(state,item)[ID] >= num: return []
	return False

def produce_enough(state, ID, item, num):
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
		subtasks.append(('op_{}'.format(name.replace(' ', '_')), ID))
		return subtasks

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

	def heuristic(state, curr_task, tasks, plan, depth, calling_stack):
		# If time goes negative, the plan is invalid.
		if state.time[ID] < 0:
			return True
		# Prevent obvious recursion cycles (e.g., trying to produce the same task again).
		if curr_task in calling_stack:
			return True
		if isinstance(curr_task, tuple):
			task_name = curr_task[0]
			if task_name == 'have_enough':
				item = curr_task[2]
				required = curr_task[3]
				# If we need more of an item and no recipe can produce it, prune.
				if getattr(state, item)[ID] < required and item not in producible:
					return True
			elif task_name == 'produce':
				item = curr_task[2]
				# Tools aren't consumed; avoid crafting duplicates.
				if item in tools and getattr(state, item)[ID] >= 1:
					return True
			elif task_name.startswith('produce_'):
				item = task_name.replace('produce_', '', 1)
				if item in tools and getattr(state, item)[ID] >= 1:
					return True
		return False # if True, prune this branch

	pyhop.add_check(heuristic)

def define_ordering(data, ID):
	# if needed, use the function below to return a different ordering for the methods
	# note that this should always return the same methods, in a new order, and should not add/remove any new ones
	def reorder_methods(state, curr_task, tasks, plan, depth, calling_stack, methods):
		return methods
	
	pyhop.define_ordering(reorder_methods)

def set_up_state(data, ID):
	state = pyhop.State('state')
	setattr(state, 'time', {ID: data['Problem']['Time']})

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
