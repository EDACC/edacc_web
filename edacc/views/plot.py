# -*- coding: utf-8 -*-
"""
    edacc.views.plot
    ----------------

    Plot view functions.
    The handlers defined in this module return the plotted images as
    HTTP responses.

    :copyright: (c) 2010 by Daniel Diepold.
    :license: MIT, see LICENSE for details.
"""

import os
import numpy
import StringIO
import csv
import random
random.seed()

from sqlalchemy import or_, not_

from flask import Module, render_template as render
from flask import Response, abort, request, g
from werkzeug import Headers, secure_filename

from edacc import plots, config, models
from sqlalchemy.orm import joinedload
from edacc.views.helpers import require_phase, require_login
from edacc.constants import ANALYSIS1, ANALYSIS2

plot = Module(__name__)


def filter_results(l1, l2):
    """Filter the lists l1 and l2 pairwise for None elements in either
    pair component. Only elements i with l1[i] == l2[i] != None remain.
    """
    r1 = [l1[i] for i in xrange(len(l1)) if l1[i] is not None and l2[i] is not None]
    r2 = [l2[i] for i in xrange(len(l2)) if l2[i] is not None and l1[i] is not None]
    return r1, r2

def scatter_2solver_1property_points(db, exp, sc1, sc2, instances, result_property, run):
    results1 = db.session.query(db.ExperimentResult)
    results1.enable_eagerloads(True).options(joinedload(db.ExperimentResult.instance, db.ExperimentResult.solver_configuration))
    results1.options(joinedload(db.ExperimentResult.properties), joinedload(db.ExperimentResult.instance))
    results1 = results1.filter_by(experiment=exp, solver_configuration=sc1).order_by(db.ExperimentResult.run)

    results2 = db.session.query(db.ExperimentResult)
    results2.enable_eagerloads(True).options(joinedload(db.ExperimentResult.instance, db.ExperimentResult.solver_configuration))
    results2.options(joinedload(db.ExperimentResult.properties), joinedload(db.ExperimentResult.instance))
    results2 = results2.filter_by(experiment=exp, solver_configuration=sc2).order_by(db.ExperimentResult.run)

    points = []
    if run == 'average':
        for instance in instances:
            r1 = [j.get_property_value(result_property, db) for j in results1.filter_by(instance=instance).all()]
            r2 = [j.get_property_value(result_property, db) for j in results2.filter_by(instance=instance).all()]
            r1, r2 = filter_results(r1, r2)
            if len(r1) > 0 and len(r2) > 0:
                s1_avg = numpy.average(r1)
                s2_avg = numpy.average(r2)
                points.append((s1_avg, s2_avg, instance))
    elif run == 'median':
        for instance in instances:
            r1 = [j.get_property_value(result_property, db) for j in results1.filter_by(instance=instance).all()]
            r2 = [j.get_property_value(result_property, db) for j in results2.filter_by(instance=instance).all()]
            r1, r2 = filter_results(r1, r2)
            if len(r1) > 0 and len(r2) > 0:
                x = numpy.median(r1)
                y = numpy.median(r2)
                points.append((x, y, instance))
    elif run == 'all':
        for instance in instances:
            xs = [j.get_property_value(result_property, db) for j in results1.filter_by(instance=instance).all()]
            ys = [j.get_property_value(result_property, db) for j in results2.filter_by(instance=instance).all()]
            xs, ys = filter_results(xs, ys)
            if len(xs) > 0 and len(ys) > 0:
                points += zip(xs, ys, [instance] * len(xs))
    else:
        for instance in instances:
            r1 = results1.filter_by(instance=instance, run=int(run)).first()
            r2 = results2.filter_by(instance=instance, run=int(run)).first()
            if r1.get_property_value(result_property, db) is not None and r2.get_property_value(result_property, db) is not None:
                points.append((
                    r1.get_property_value(result_property, db),
                    r2.get_property_value(result_property, db),
                    instance
                ))

    return points


@plot.route('/<database>/experiment/<int:experiment_id>/scatter-plot-1property/')
@require_phase(phases=ANALYSIS2)
@require_login
def scatter_2solver_1property(database, experiment_id):
    """Returns an image with a scatter plot of the result property of two
    solver configurations' results on instances as HTTP response.

    The data to be plotted has to be specified as GET parameters:

    solver_config1: id of the first solver configuration
    solver_config2: id of the second solver configuratio
    instances: id of an instance, multiple occurences allowed.
    run: 'average', 'median', 'all', or an integer of the run.
            If the value is 'all', all runs of the solvers will be plotted.
            If the value is 'average' or 'median', these values will be calculated
            across multiple runs of one solver on an instance.
            If the value is an integer, the data of this specific run is used.
    result_property: id of a result property (Property table) or the special case
                     'cputime' for the time column of the ExperimentResult table.
    """
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    s1 = int(request.args['solver_config1'])
    s2 = int(request.args['solver_config2'])

    instances = [db.session.query(db.Instance).filter(db.Instance.idInstance.in_(map(int, request.args.getlist('i')))).all()]
    instance_groups_count = int(request.args.get('instance_groups_count', 1))
    for i in xrange(1, instance_groups_count):
        instances.append(db.session.query(db.Instance).filter(db.Instance.idInstance.in_(map(int, request.args.getlist('i'+str(i))))).all())

    run = request.args['run']
    xscale = request.args['xscale']
    yscale = request.args['yscale']
    result_property = request.args['result_property']
    if result_property != 'cputime':
        solver_prop = db.session.query(db.Property).get(int(result_property))

    sc1 = db.session.query(db.SolverConfiguration).get(s1) or abort(404)
    sc2 = db.session.query(db.SolverConfiguration).get(s2) or abort(404)

    points = []
    for instance_group in instances:
        points.append(scatter_2solver_1property_points(db, exp, sc1, sc2, instance_group, result_property, run))

    max_x = max([max([p[0] for p in ig] or [0]) for ig in points] or [0])
    max_y = max([max([p[1] for p in ig] or [0]) for ig in points] or [0])
    max_x = max_y = max(max_x, max_y) * 1.1

    title = sc1.get_name() + ' vs. ' + sc2.get_name()
    if result_property == 'cputime':
        xlabel = sc1.get_name() + ' CPU Time'
        ylabel = sc2.get_name() + ' CPU Time'
    else:
        xlabel = sc1.get_name() + ' ' + solver_prop.name
        ylabel = sc2.get_name() + ' ' + solver_prop.name

    if request.args.has_key('csv'):
        csv_response = StringIO.StringIO()
        csv_writer = csv.writer(csv_response)
        csv_writer.writerow(['Instance', xlabel, ylabel])
        for ig in points:
            for x, y, i in ig:
                csv_writer.writerow([str(i), x, y])
        csv_response.seek(0)

        headers = Headers()
        headers.add('Content-Type', 'text/csv')
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_scatter_" + sc1.get_name() + '_vs_' + sc2.get_name() + ".csv"))
        return Response(response=csv_response.read(), headers=headers)
    elif request.args.has_key('pdf'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.pdf'
        plots.scatter(points, xlabel, ylabel, title, max_x, max_y, filename, format='pdf', xscale=xscale, yscale=yscale, diagonal_line=True)
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(sc1.get_name() + '_vs_' + sc2.get_name() + '.pdf'))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/pdf', headers=headers)
        os.remove(filename)
        return response
    elif request.args.has_key('eps'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.eps'
        plots.scatter(points, xlabel, ylabel, title, max_x, max_y, filename, format='eps', xscale=xscale, yscale=yscale, diagonal_line=True)
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(sc1.get_name() + '_vs_' + sc2.get_name() + '.eps'))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/eps', headers=headers)
        os.remove(filename)
        return response
    elif request.args.has_key('rscript'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.txt'
        plots.scatter(points, xlabel, ylabel, title, max_x, max_y, filename, format='rscript', xscale=xscale, yscale=yscale, diagonal_line=True)
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(sc1.get_name() + '_vs_' + sc2.get_name() + '.txt'))
        response = Response(response=open(filename, 'rb').read(), mimetype='text/plain', headers=headers)
        os.remove(filename)
        return response
    else:
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.png'
        pts = plots.scatter(points, xlabel, ylabel, title, max_x, max_y, filename, xscale=xscale, yscale=yscale, diagonal_line=True)
        pts2 = []
        for j in xrange(len(points)):
            pts2 += [(pts[j][i][0], pts[j][i][1], points[j][i][0], points[j][i][1], points[j][i][2]) for i in xrange(len(points[j]))]
        if request.args.has_key('imagemap'):
            return render('/analysis/imagemap_2solver_1property.html', database=database, points=pts2, sc1=sc1, sc2=sc2)
        else:
            response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
        os.remove(filename)
        return response


def scatter_1solver_instance_vs_result_property_points(db, exp, solver_config, instances, instance_property, result_property, run):
    results = db.session.query(db.ExperimentResult)
    results.enable_eagerloads(True).options(joinedload(db.ExperimentResult.instance, db.ExperimentResult.solver_configuration))
    results = results.filter_by(experiment=exp, solver_configuration=solver_config)

    points = []
    if run == 'average':
        for instance in instances:
            prop_value = instance.get_property_value(instance_property, db)
            res = [j.get_property_value(result_property, db) for j in results.filter_by(instance=instance).all()]
            res = filter(lambda r: r is not None, res)
            if res != [] and prop_value is not None:
                s_avg = numpy.average(res)
                points.append((prop_value, s_avg, instance))
    elif run == 'median':
        for instance in instances:
            prop_value = instance.get_property_value(instance_property, db)
            res = [j.get_property_value(result_property, db) for j in results.filter_by(instance=instance).all()]
            res = filter(lambda r: r is not None, res)
            if res != [] and prop_value is not None:
                y = numpy.median(res)
                points.append((prop_value, y, instance))
    elif run == 'all':
        for instance in instances:
            prop_value = instance.get_property_value(instance_property, db)
            if prop_value is not None:
                xs = [prop_value] * len(results.filter_by(instance=instance).all())
                ys = [j.get_property_value(result_property, db) for j in results.filter_by(instance=instance).all()]
                ys = filter(lambda r: r is not None, ys)
                points += zip(xs, ys, [instance] * len(xs))
    else:
        for instance in instances:
            res = results.filter_by(instance=instance, run=int(run)).first()
            if instance.get_property_value(instance_property, db) is not None and res.get_property_value(result_property, db) is not None:
                points.append((
                    instance.get_property_value(instance_property, db),
                    res.get_property_value(result_property, db),
                    instance
                ))

    return points


@plot.route('/<database>/experiment/<int:experiment_id>/scatter-plot-instance-vs-result/')
@require_phase(phases=ANALYSIS2)
@require_login
def scatter_1solver_instance_vs_result_property(database, experiment_id):
    """ Returns an image with the result property values of one solver
    against the instance property values, e.g. CPU time vs memory used.
    """
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    solver_config = int(request.args['solver_config'])
    run = request.args['run']
    xscale = request.args['xscale']
    yscale = request.args['yscale']
    result_property = request.args['result_property']
    instance_property = request.args['instance_property']

    instances = [db.session.query(db.Instance).filter(db.Instance.idInstance.in_(map(int, request.args.getlist('i')))).all()]
    instance_groups_count = int(request.args.get('instance_groups_count', 1))
    for i in xrange(1, instance_groups_count):
        instances.append(db.session.query(db.Instance).filter(db.Instance.idInstance.in_(map(int, request.args.getlist('i'+str(i))))).all())

    if result_property != 'cputime':
        solver_prop = db.session.query(db.Property).get(int(result_property))

    instance_prop = db.session.query(db.Property).get(int(instance_property))

    solver_config = db.session.query(db.SolverConfiguration).get(solver_config) or abort(404)

    points = []
    for instance_group in instances:
        points.append(scatter_1solver_instance_vs_result_property_points(db, exp, solver_config, instance_group, int(instance_property), result_property, run))

    xlabel = instance_prop.name

    if result_property == 'cputime':
        ylabel = 'CPU Time'
    else:
        ylabel = solver_prop.name

    title = str(solver_config)

    max_x = max([max([p[0] for p in ig] or [0]) for ig in points] or [0]) * 1.1
    max_y = max([max([p[1] for p in ig] or [0]) for ig in points] or [0]) * 1.1

    if request.args.has_key('csv'):
        csv_response = StringIO.StringIO()
        csv_writer = csv.writer(csv_response)
        csv_writer.writerow(['Instance', xlabel, ylabel])
        for x, y, i in points:
            csv_writer.writerow([str(i), x, y])
        csv_response.seek(0)

        headers = Headers()
        headers.add('Content-Type', 'text/csv')
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_scatter_" + str(solver_config) + "_" + ylabel + "_vs_" + xlabel + ".csv"))
        return Response(response=csv_response.read(), headers=headers)
    elif request.args.has_key('pdf'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.pdf'
        plots.scatter(points, xlabel, ylabel, title, max_x, max_y, filename, format='pdf', xscale=xscale, yscale=yscale)
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_scatter_" + str(solver_config) + "_" + ylabel + "_vs_" + xlabel + '.pdf'))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/pdf', headers=headers)
        os.remove(filename)
        return response
    elif request.args.has_key('eps'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.eps'
        plots.scatter(points, xlabel, ylabel, title, max_x, max_y, filename, format='eps', xscale=xscale, yscale=yscale)
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_scatter_" + str(solver_config) + "_" + ylabel + "_vs_" + xlabel + '.eps'))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/eps', headers=headers)
        os.remove(filename)
        return response
    elif request.args.has_key('rscript'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.txt'
        plots.scatter(points, xlabel, ylabel, title, max_x, max_y, filename, format='rscript', xscale=xscale, yscale=yscale, diagonal_line=True)
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_scatter_" + str(solver_config) + "_" + ylabel + "_vs_" + xlabel + '.txt'))
        response = Response(response=open(filename, 'rb').read(), mimetype='text/plain', headers=headers)
        os.remove(filename)
        return response
    else:
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.png'
        pts = plots.scatter(points, xlabel, ylabel, title, max_x, max_y, filename, xscale=xscale, yscale=yscale)
        pts2 = []
        for j in xrange(len(points)):
            pts2 += [(pts[j][i][0], pts[j][i][1], points[j][i][0], points[j][i][1], points[j][i][2]) for i in xrange(len(points[j]))]
        if request.args.has_key('imagemap'):
            return render('/analysis/imagemap_instance_vs_result.html', database=database, points=pts2, sc=solver_config)
        else:
            response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
        os.remove(filename)
        return response


def scatter_1solver_result_vs_result_property_plot(db, exp, solver_config, instances, result_property1, result_property2, run):
    results = db.session.query(db.ExperimentResult)
    results.enable_eagerloads(True).options(joinedload(db.ExperimentResult.instance, db.ExperimentResult.solver_configuration))
    results = results.filter_by(experiment=exp, solver_configuration=solver_config).order_by(db.ExperimentResult.run)

    points = []
    if run == 'average':
        for instance in instances:
            r1 = [j.get_property_value(result_property1, db) for j in results.filter_by(instance=instance).all()]
            r2 = [j.get_property_value(result_property2, db) for j in results.filter_by(instance=instance).all()]
            r1, r2 = filter_results(r1, r2)
            if len(r1) > 0 and len(r2) > 0:
                s1_avg = numpy.average(r1)
                s2_avg = numpy.average(r2)
                points.append((s1_avg, s2_avg, instance))
    elif run == 'median':
        for instance in instances:
            r1 = [j.get_property_value(result_property1, db) for j in results.filter_by(instance=instance).all()]
            r2 = [j.get_property_value(result_property2, db) for j in results.filter_by(instance=instance).all()]
            r1, r2 = filter_results(r1, r2)
            if len(r1) > 0 and len(r2) > 0:
                x = numpy.median(r1)
                y = numpy.median(r2)
                points.append((x, y, instance))
    elif run == 'all':
        for instance in instances:
            xs = [j.get_property_value(result_property1, db) for j in results.filter_by(instance=instance).all()]
            ys = [j.get_property_value(result_property2, db) for j in results.filter_by(instance=instance).all()]
            xs, ys = filter_results(xs, ys)
            if len(xs) > 0 and len(ys) > 0:
                points += zip(xs, ys, [instance] * len(xs))
    else:
        for instance in instances:
            res = results.filter_by(instance=instance, run=int(run)).first()
            if res.get_property_value(result_property1, db) is not None and res.get_property_value(result_property2, db) is not None:
                points.append((
                    res.get_property_value(result_property1, db),
                    res.get_property_value(result_property2, db),
                    instance
                ))

    return points


@plot.route('/<database>/experiment/<int:experiment_id>/scatter-plot-2properties/')
@require_phase(phases=ANALYSIS2)
@require_login
def scatter_1solver_result_vs_result_property(database, experiment_id):
    """ Returns an image with the result property values against
    other result property values.
    """
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    solver_config = int(request.args['solver_config'])
    run = request.args['run']
    xscale = request.args['xscale']
    yscale = request.args['yscale']
    result_property1 = request.args['result_property1']
    result_property2 = request.args['result_property2']

    instances = [db.session.query(db.Instance).filter(db.Instance.idInstance.in_(map(int, request.args.getlist('i')))).all()]
    instance_groups_count = int(request.args.get('instance_groups_count', 1))
    for i in xrange(1, instance_groups_count):
        instances.append(db.session.query(db.Instance).filter(db.Instance.idInstance.in_(map(int, request.args.getlist('i'+str(i))))).all())

    if result_property1 != 'cputime':
        solver_prop1 = db.session.query(db.Property).get(int(result_property1))

    if result_property2 != 'cputime':
        solver_prop2 = db.session.query(db.Property).get(int(result_property2))

    solver_config = db.session.query(db.SolverConfiguration).get(solver_config) or abort(404)

    points = []
    for instance_group in instances:
        points.append( scatter_1solver_result_vs_result_property_plot(db, exp, solver_config, instance_group, result_property1, result_property2, run))

    if result_property1 == 'cputime':
        xlabel = 'CPU Time'
    else:
        xlabel = solver_prop1.name

    if result_property2 == 'cputime':
        ylabel = 'CPU Time'
    else:
        ylabel = solver_prop2.name

    title = str(solver_config)

    max_x = max([max([p[0] for p in ig] or [0]) for ig in points] or [0]) * 1.1
    max_y = max([max([p[1] for p in ig] or [0]) for ig in points] or [0]) * 1.1

    if request.args.has_key('csv'):
        csv_response = StringIO.StringIO()
        csv_writer = csv.writer(csv_response)
        csv_writer.writerow(['Instance', xlabel, ylabel])
        for x, y, i in points:
            csv_writer.writerow([str(i), x, y])
        csv_response.seek(0)

        headers = Headers()
        headers.add('Content-Type', 'text/csv')
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_scatter_" + str(solver_config) + "_" + ylabel + "_vs_" + xlabel + '.csv'))
        return Response(response=csv_response.read(), headers=headers)
    elif request.args.has_key('pdf'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.pdf'
        plots.scatter(points, xlabel, ylabel, title, max_x, max_y, filename, format='pdf', xscale=xscale, yscale=yscale)
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_scatter_" + str(solver_config) + "_" + ylabel + "_vs_" + xlabel + '.pdf'))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/pdf', headers=headers)
        os.remove(filename)
        return response
    elif request.args.has_key('eps'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.eps'
        plots.scatter(points, xlabel, ylabel, title, max_x, max_y, filename, format='eps', xscale=xscale, yscale=yscale)
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_scatter_" + str(solver_config) + "_" + ylabel + "_vs_" + xlabel + '.eps'))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/eps', headers=headers)
        os.remove(filename)
        return response
    elif request.args.has_key('rscript'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.txt'
        plots.scatter(points, xlabel, ylabel, title, max_x, max_y, filename, format='rscript', xscale=xscale, yscale=yscale, diagonal_line=True)
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_scatter_" + str(solver_config) + "_" + ylabel + "_vs_" + xlabel + '.txt'))
        response = Response(response=open(filename, 'rb').read(), mimetype='text/plain', headers=headers)
        os.remove(filename)
        return response
    else:
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.png'
        pts = plots.scatter(points, xlabel, ylabel, title, max_x, max_y, filename, xscale=xscale, yscale=yscale)
        pts2 = []
        for j in xrange(len(points)):
            pts2 += [(pts[j][i][0], pts[j][i][1], points[j][i][0], points[j][i][1], points[j][i][2]) for i in xrange(len(points[j]))]
        if request.args.has_key('imagemap'):
            return render('/analysis/imagemap_result_vs_result.html', database=database, points=pts2, sc=solver_config)
        else:
            response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
        os.remove(filename)
        return response


@plot.route('/<database>/experiment/<int:experiment_id>/cactus-plot/')
@require_phase(phases=ANALYSIS1)
@require_login
def cactus_plot(database, experiment_id):
    """ Renders a cactus plot of the instances solved within a given "amount" of
        a result property of all solver configurations of the specified
        experiment
    """
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    instance_groups_count = int(request.args.get('instance_groups_count', 0))
    use_colors_for = request.args.get('use_colors_for', 'solvers')
    colored_instance_groups = (use_colors_for == 'instance_groups')
    log_property = request.args.has_key('log_property')
    flip_axes = request.args.has_key('flip_axes')
    run = request.args.get('run', 'all')

    results = db.session.query(db.ExperimentResult)
    results.enable_eagerloads(True).options(joinedload(db.ExperimentResult.solver_configuration))
    results.options(joinedload(db.ExperimentResult.properties))
    results = results.filter_by(experiment=exp)
    instances = [[int(id) for id in request.args.getlist('i')]]
    for i in xrange(1, instance_groups_count):
        instances.append([int(id) for id in request.args.getlist('i'+str(i))])

    result_property = request.args.get('result_property') or 'cputime'
    if result_property != 'cputime':
        solver_prop = db.session.query(db.Property).get(int(result_property))

    solver_configs = [db.session.query(db.SolverConfiguration).get(int(id)) for id in request.args.getlist('sc')]

    solvers = []

    random_run = random.randint(0, exp.get_num_runs(db) - 1)

    for instance_group in xrange(instance_groups_count):
        for sc in solver_configs:
            s = {'xs': [], 'ys': [], 'name': sc.get_name(), 'instance_group': instance_group}
            sc_res = results.filter_by(solver_configuration=sc, status=1).filter(db.ExperimentResult.resultCode.like('1%')) \
                             .filter(db.ExperimentResult.Instances_idInstance.in_(instances[instance_group]))
            if run == 'all':
                sc_results = filter(lambda j: j is not None, [r.get_property_value(result_property, db) for r in sc_res.all()])
            elif run in ('average', 'median'):
                sc_results = []
                for id in instances[instance_group]:
                    res = sc_res.filter(db.ExperimentResult.Instances_idInstance==id).all()
                    res = [r.get_property_value(result_property, db) for r in res]
                    res = filter(lambda r: r is not None, res)
                    if len(res) > 0:
                        if run == 'average':
                            sc_results.append(numpy.average(res))
                        elif run == 'median':
                            sc_results.append(numpy.median(res or [0]))
            elif run == 'random':
                sc_results = [r.get_property_value(result_property, db) for r in sc_res.filter_by(run=random_run).all()]
                sc_results = filter(lambda r: r is not None, sc_results)
            elif run == 'penalized_average':
                sc_results = []
                for id in instances[instance_group]:
                    res = sc_res.filter(db.ExperimentResult.Instances_idInstance==id).all()
                    res = [r.get_property_value(result_property, db) for r in res]
                    num_penalized = results.filter_by(solver_configuration=sc) \
                                        .filter(db.ExperimentResult.Instances_idInstance==id) \
                                        .filter(or_(db.ExperimentResult.status!=1,
                                                    not_(db.ExperimentResult.resultCode.like('1%')))).count()
                    if result_property == 'cputime':
                        penalized_time = sum([j.CPUTimeLimit * 10.0 for j in res if not str(res.resultCode).startswith('1')])
                    else:
                        penalized_time = 0
                    penalized_avg = (sum(res) + penalized_time) / (num_penalized + len(res))
                    sc_results.append(penalized_avg)
            else:
                run_number = int(run)
                res = sc_res.filter_by(run=run_number).all()
                res = [r.get_property_value(result_property, db) for r in res]
                sc_results = filter(lambda r: r is not None, res)

            sc_results = sorted(sc_results)
            if not log_property:
                s['ys'].append(0)
                s['xs'].append(0)

            # sc_results = (y_1, y_2, ..., y_n) : y_1 <= y_2 <= ... <= y_n
            # s = {(x, y) \in R² : y = sc_results[x], x = 1, ..., n }
            i = 1
            for r in sc_results:
                s['ys'].append(r)
                s['xs'].append(i)
                i += 1
            solvers.append(s)

    min_y = min([min(s['xs'] or [0.1]) for s in solvers] or [0.1])
    max_x = max([max(s['xs'] or [0]) for s in solvers] or [0]) + 10
    max_y = max([max(s['ys'] or [0]) for s in solvers] or [0]) * 1.1

    if result_property == 'cputime':
        ylabel = 'CPU Time (s)'
        title = 'Number of solved instances within a given amount of CPU time'
    else:
        ylabel = solver_prop.name
        title = 'Number of solved instances within a given amount of ' + solver_prop.name

    if request.args.has_key('csv'):
        csv_response = StringIO.StringIO()
        csv_writer = csv.writer(csv_response)
        for s in solvers:
            csv_writer.writerow(['%s (G%d)' % (s['name'], s['instance_group'])])
            csv_writer.writerow(['number of solved instances'] + map(str, s['xs']))
            csv_writer.writerow(['CPU Time (s)'] + map(str, s['ys']))
        csv_response.seek(0)

        headers = Headers()
        headers.add('Content-Type', 'text/csv')
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_cactus.csv"))
        return Response(response=csv_response.read(), headers=headers)
    elif request.args.has_key('pdf'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'cactus.pdf'
        plots.cactus(solvers, instance_groups_count, colored_instance_groups, max_x, max_y, min_y, log_property, flip_axes, ylabel, title, filename, format='pdf')
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + '_cactus.pdf'))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/pdf', headers=headers)
        os.remove(filename)
        return response
    elif request.args.has_key('eps'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'cactus.eps'
        plots.cactus(solvers, instance_groups_count, colored_instance_groups, max_x, max_y, min_y, log_property, flip_axes, ylabel, title, filename, format='eps')
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + '_cactus.eps'))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/eps', headers=headers)
        os.remove(filename)
        return response
    elif request.args.has_key('rscript'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.txt'
        plots.cactus(solvers, instance_groups_count, colored_instance_groups, max_x, max_y, min_y, log_property, flip_axes, ylabel, title, filename, format='rscript')
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + '_cactus.txt'))
        response = Response(response=open(filename, 'rb').read(), mimetype='text/plain', headers=headers)
        os.remove(filename)
        return response
    else:
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'cactus.png'
        plots.cactus(solvers, instance_groups_count, colored_instance_groups, max_x, max_y, min_y, log_property, flip_axes, ylabel, title, filename)
        response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
        os.remove(filename)
        return response


@plot.route('/<database>/experiment/<int:experiment_id>/rp-comparison-plot/')
@require_phase(phases=ANALYSIS2)
@require_login
def result_property_comparison_plot(database, experiment_id):
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    instance = db.session.query(db.Instance).filter_by(idInstance=int(request.args['instance'])).first() or abort(404)
    s1 = db.session.query(db.SolverConfiguration).get(int(request.args['solver_config1'])) or abort(404)
    s2 = db.session.query(db.SolverConfiguration).get(int(request.args['solver_config2'])) or abort(404)
    dim = int(request.args.get('dim', 700))

    log_property = request.args.has_key('log_property')
    result_property = request.args.get('result_property')
    if result_property != 'cputime':
        result_property = db.session.query(db.Property).get(int(result_property)).idProperty
        result_property_name = db.session.query(db.Property).get(int(result_property)).name
    else:
        result_property_name = 'CPU time (s)'

    results1 = [r.get_property_value(result_property, db) for r in db.session.query(db.ExperimentResult)
                                    .filter_by(experiment=exp,
                                               solver_configuration=s1,
                                               instance=instance).all()]
    results2 = [r.get_property_value(result_property, db) for r in db.session.query(db.ExperimentResult)
                                    .filter_by(experiment=exp,
                                               solver_configuration=s2,
                                               instance=instance).all()]

    results1 = filter(lambda r: r is not None, results1)
    results2 = filter(lambda r: r is not None, results2)

    if request.args.has_key('csv'):
        csv_response = StringIO.StringIO()
        csv_writer = csv.writer(csv_response)
        csv_writer.writerow([result_property_name + ' results of the two solver configurations on ' + str(instance)])
        csv_writer.writerow([str(s1), str(s2)])
        for i in xrange(min(len(results1), len(results2))):
            csv_writer.writerow(map(str, [results1[i], results2[i]]))
        csv_response.seek(0)

        headers = Headers()
        headers.add('Content-Type', 'text/csv')
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_" + str(s1) + "_" + str(s2) + "result_comparison.csv"))
        return Response(response=csv_response.read(), headers=headers)
    elif request.args.has_key('pdf'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'rtdcomp.pdf'
        plots.result_property_comparison(results1, results2, str(s1), str(s2), result_property_name, log_property, filename, format='pdf', dim=dim)
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_" + str(s1) + "_" + str(s2) + "result_comparison.pdf"))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/pdf', headers=headers)
        os.remove(filename)
        return response
    elif request.args.has_key('eps'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'rtdcomp.eps'
        plots.result_property_comparison(results1, results2, str(s1), str(s2), result_property_name, log_property, filename, format='eps', dim=dim)
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_" + str(s1) + "_" + str(s2) + "result_comparison.eps"))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/eps', headers=headers)
        os.remove(filename)
        return response
    else:
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'rtdcomp.png'
        plots.result_property_comparison(results1, results2, str(s1), str(s2), result_property_name, log_property, filename, 'png', dim=dim)
        response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
        os.remove(filename)
        return response


@plot.route('/<database>/experiment/<int:experiment_id>/rps-plot/')
@require_phase(phases=ANALYSIS2)
@require_login
def property_distributions_plot(database, experiment_id):
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    instance = db.session.query(db.Instance).filter_by(idInstance=int(request.args['instance'])).first() or abort(404)
    solver_configs = [db.session.query(db.SolverConfiguration).get(int(id)) for id in request.args.getlist('sc')]

    log_property = request.args.has_key('log_property')
    result_property = request.args.get('result_property')
    if result_property != 'cputime':
        result_property = db.session.query(db.Property).get(int(result_property)).idProperty
        result_property_name = db.session.query(db.Property).get(int(result_property)).name
    else:
        result_property_name = 'CPU time (s)'

    results = []
    for sc in solver_configs:
        sc_results = db.session.query(db.ExperimentResult) \
                        .filter_by(experiment=exp, instance=instance,
                                   solver_configuration=sc).all()
        results.append((sc, filter(lambda i: i is not None, [j.get_property_value(result_property, db) for j in sc_results])))

    if request.args.has_key('csv'):
        csv_response = StringIO.StringIO()
        csv_writer = csv.writer(csv_response)
        csv_writer.writerow([result_property_name + ' values of the listed solver configurations on ' + str(instance)])
        for res in results:
            csv_writer.writerow([str(res[0])] + map(str, res[1]))
        csv_response.seek(0)

        headers = Headers()
        headers.add('Content-Type', 'text/csv')
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_rtds.csv"))
        return Response(response=csv_response.read(), headers=headers)
    elif request.args.has_key('pdf'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'rtds.png'
        plots.property_distributions(results, filename, result_property_name, log_property, 'pdf')
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_rtds.pdf"))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/pdf', headers=headers)
        os.remove(filename)
        return response
    elif request.args.has_key('eps'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'rtds.eps'
        plots.property_distributions(results, filename, result_property_name, log_property, 'eps')
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_rtds.eps"))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/eps', headers=headers)
        os.remove(filename)
        return response
    else:
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'rtds.png'
        plots.property_distributions(results, filename, result_property_name, log_property, 'png')
        response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
        os.remove(filename)
        return response


@plot.route('/<database>/experiment/<int:experiment_id>/rp-plot/')
@require_phase(phases=ANALYSIS2)
@require_login
def property_distribution(database, experiment_id):
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)
    sc = db.session.query(db.SolverConfiguration).get(int(request.args['solver_config'])) or abort(404)
    instance = db.session.query(db.Instance).filter_by(idInstance=int(request.args['instance'])).first() or abort(404)

    log_property = request.args.has_key('log_property')
    result_property = request.args.get('result_property')
    if result_property != 'cputime':
        result_property = db.session.query(db.Property).get(int(result_property)).idProperty
        result_property_name = db.session.query(db.Property).get(int(result_property)).name
    else:
        result_property_name = 'CPU time (s)'

    results = [r.get_property_value(result_property, db) for r in db.session.query(db.ExperimentResult)
                                    .filter_by(experiment=exp,
                                               solver_configuration=sc,
                                               instance=instance).all()]

    results = filter(lambda r: r is not None, results)

    if request.args.has_key('csv'):
        csv_response = StringIO.StringIO()
        csv_writer = csv.writer(csv_response)
        csv_writer.writerow([result_property_name + ' of ' + str(sc) + ' on ' + str(instance)])
        csv_writer.writerow(map(str, results))
        csv_response.seek(0)

        headers = Headers()
        headers.add('Content-Type', 'text/csv')
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_" + str(sc) + "_rtd.csv"))
        return Response(response=csv_response.read(), headers=headers)
    elif request.args.has_key('pdf'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'rtd.pdf'
        plots.property_distribution(results, filename, result_property_name, log_property, 'pdf')
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_" + str(sc) + "_rtd.pdf"))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/pdf', headers=headers)
        os.remove(filename)
        return response
    elif request.args.has_key('eps'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'rtd.eps'
        plots.property_distribution(results, filename, result_property_name, log_property, 'eps')
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_" + str(sc) + "_rtd.eps"))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/eps', headers=headers)
        os.remove(filename)
        return response
    else:
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'rtd.png'
        plots.property_distribution(results, filename, result_property_name, log_property, 'png')
        response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
        os.remove(filename)
        return response


@plot.route('/<database>/experiment/<int:experiment_id>/kerneldensity-plot/')
@require_phase(phases=ANALYSIS2)
@require_login
def kerneldensity(database, experiment_id):
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)
    sc = db.session.query(db.SolverConfiguration).get(int(request.args['solver_config'])) or abort(404)
    instance = db.session.query(db.Instance).filter_by(idInstance=int(request.args['instance'])).first() or abort(404)

    log_property = request.args.has_key('log_property')
    result_property = request.args.get('result_property')
    if result_property != 'cputime':
        result_property = db.session.query(db.Property).get(int(result_property)).idProperty
        result_property_name = db.session.query(db.Property).get(int(result_property)).name
    else:
        result_property_name = 'CPU time (s)'

    results = [r.get_property_value(result_property, db) for r in db.session.query(db.ExperimentResult)
                                    .filter_by(experiment=exp,
                                               solver_configuration=sc,
                                               instance=instance).all()]

    results = filter(lambda r: r is not None, results)

    if request.args.has_key('csv'):
        csv_response = StringIO.StringIO()
        csv_writer = csv.writer(csv_response)
        csv_writer.writerow([result_property_name + ' of ' + str(sc) + ' on ' + str(instance)])
        csv_writer.writerow(map(str, results))
        csv_response.seek(0)

        headers = Headers()
        headers.add('Content-Type', 'text/csv')
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_" + str(sc) + "_kerneldensity.csv"))
        return Response(response=csv_response.read(), headers=headers)
    elif request.args.has_key('pdf'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'kerneldens.pdf'
        plots.kerneldensity(results, filename, result_property_name, log_property, 'pdf')
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_" + str(sc) + "_kerneldensity.pdf"))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/pdf', headers=headers)
        os.remove(filename)
        return response
    elif request.args.has_key('eps'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'kerneldens.eps'
        plots.kerneldensity(results, filename, result_property_name, log_property, 'eps')
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_" + str(sc) + "_kerneldensity.eps"))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/pdf', headers=headers)
        os.remove(filename)
        return response
    else:
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'kerneldens.png'
        plots.kerneldensity(results, filename, result_property_name, log_property, 'png')
        response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
        os.remove(filename)
        return response


@plot.route('/<database>/experiment/<int:experiment_id>/box-plots-plot/')
@require_phase(phases=ANALYSIS2)
@require_login
def box_plots(database, experiment_id):
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    instances = db.session.query(db.Instance).filter(db.Instance.idInstance.in_(int(id) for id in request.args.getlist('i'))).all()
    solver_configs = [db.session.query(db.SolverConfiguration).get(int(id)) for id in request.args.getlist('solver_configs')]

    result_property = request.args.get('result_property')
    if result_property != 'cputime':
        result_property = db.session.query(db.Property).get(int(result_property)).idProperty
        result_property_name = db.session.query(db.Property).get(int(result_property)).name
    else:
        result_property_name = 'CPU time (s)'

    results = {}
    for sc in solver_configs:
        points = []
        for instance in instances:
            points += filter(lambda r: r is not None, [res.get_property_value(result_property, db) for res in db.session.query(db.ExperimentResult).filter_by(experiment=exp, instance=instance, solver_configuration=sc).all()])
        results[str(sc)] = points

    if request.args.has_key('csv'):
        csv_response = StringIO.StringIO()
        csv_writer = csv.writer(csv_response)
        for k, v in results.iteritems():
            csv_writer.writerow([k] + map(str, v))
        csv_response.seek(0)

        headers = Headers()
        headers.add('Content-Type', 'text/csv')
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_box_plots.csv"))
        return Response(response=csv_response.read(), headers=headers)
    elif request.args.has_key('pdf'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'boxplot.pdf'
        plots.box_plot(results, filename, result_property_name, 'pdf')
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_box_plots.pdf"))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/pdf', headers=headers)
        os.remove(filename)
        return response
    elif request.args.has_key('eps'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'boxplot.eps'
        plots.box_plot(results, filename, result_property_name, 'eps')
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=secure_filename(exp.name + "_box_plots.eps"))
        response = Response(response=open(filename, 'rb').read(), mimetype='application/eps', headers=headers)
        os.remove(filename)
        return response
    else:
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'boxplot.png'
        plots.box_plot(results, filename, result_property_name, 'png')
        response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
        os.remove(filename)
        return response


@plot.route('/<database>/experiment/<int:experiment_id>/barplot/<int:gt>/<int:eq>/<int:lt>')
@require_phase(phases=ANALYSIS2)
@require_login
def barplot(database, experiment_id, gt, eq, lt):
    filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'barplot.png'
    plots.barplot([gt, eq, lt], filename, 'png')
    response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
    os.remove(filename)
    return response