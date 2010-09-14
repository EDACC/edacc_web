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
import json
import numpy
import StringIO
import csv

from flask import Module
from flask import render_template, url_for
from flask import Response, abort, request, g
from werkzeug import Headers

from edacc import plots, config, models, forms, ranking
from sqlalchemy.orm import joinedload
from edacc.views.helpers import require_phase, require_login

plot = Module(__name__)


@plot.route('/<database>/experiment/<int:experiment_id>/scatter-plot-1property/')
@require_phase(phases=(5, 6, 7))
@require_login
def scatter_2solver_1property(database, experiment_id):
    """ description """
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    s1 = int(request.args['solver_config1'])
    s2 = int(request.args['solver_config2'])
    instances = [db.session.query(db.Instance).filter_by(idInstance=int(id)).first() for id in request.args.getlist('instances')]
    run = request.args['run']
    scaling = request.args['scaling']
    solver_property = request.args['solver_property']
    if solver_property != 'cputime':
        solver_prop = db.session.query(db.SolverProperty).get(int(solver_property))

    sc1 = db.session.query(db.SolverConfiguration).get(s1) or abort(404)
    sc2 = db.session.query(db.SolverConfiguration).get(s2) or abort(404)

    results1 = db.session.query(db.ExperimentResult)
    results1.enable_eagerloads(True).options(joinedload(db.ExperimentResult.instance, db.ExperimentResult.solver_configuration))
    results1 = results1.filter_by(experiment=exp, solver_configuration=sc1)

    results2 = db.session.query(db.ExperimentResult)
    results2.enable_eagerloads(True).options(joinedload(db.ExperimentResult.instance, db.ExperimentResult.solver_configuration))
    results2 = results2.filter_by(experiment=exp, solver_configuration=sc2)

    points = []
    if run == 'average':
        for instance in instances:
            s1_avg = numpy.average([j.get_property_value(solver_property, db) for j in results1.filter_by(instance=instance).all()])
            s2_avg = numpy.average([j.get_property_value(solver_property, db) for j in results2.filter_by(instance=instance).all()])
            points.append((s1_avg, s2_avg, instance))
    elif run == 'median':
        for instance in instances:
            x = numpy.median([j.get_property_value(solver_property, db) for j in results1.filter_by(instance=instance).all()])
            y = numpy.median([j.get_property_value(solver_property, db) for j in results2.filter_by(instance=instance).all()])
            points.append((x, y, instance))
    elif run == 'all':
        for instance in instances:
            xs = [j.get_property_value(solver_property, db) for j in results1.filter_by(instance=instance).all()]
            ys = [j.get_property_value(solver_property, db) for j in results2.filter_by(instance=instance).all()]
            points += zip(xs, ys, [instance] * len(xs))
    else:
        for instance in instances:
            r1 = results1.filter_by(instance=instance, run=int(run)).first()
            r2 = results2.filter_by(instance=instance, run=int(run)).first()
            points.append((
                r1.get_property_value(solver_property, db),
                r2.get_property_value(solver_property, db),
                instance
            ))

    title = sc1.solver.name + ' vs. ' + sc2.solver.name
    if solver_property == 'cputime':
        xlabel = sc1.solver.name + ' CPU Time'
        ylabel = sc2.solver.name + ' CPU Time'
    else:
        xlabel = sc1.solver.name + ' ' + solver_prop.name
        ylabel = sc2.solver.name + ' ' + solver_prop.name

    if request.args.has_key('csv'):
        csv_response = StringIO.StringIO()
        csv_writer = csv.writer(csv_response)
        csv_writer.writerow(['Instance', "CPU Time (s) " + str(sc1), "CPU Time (s) " + str(sc2)])
        for x, y, i in points:
            csv_writer.writerow([str(i), x, y])
        csv_response.seek(0)

        headers = Headers()
        headers.add('Content-Type', 'text/csv')
        headers.add('Content-Disposition', 'attachment', filename="data.csv")
        return Response(response=csv_response.read(), headers=headers)

    elif request.args.has_key('pdf'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.pdf'
        plots.scatter(points, xlabel, ylabel, title, exp.timeOut, filename, format='pdf', scaling=scaling)
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=sc1.solver.name + '_vs_' + sc2.solver.name + '.pdf')
        response = Response(response=open(filename, 'rb').read(), mimetype='application/pdf', headers=headers)
        os.remove(filename)
        return response
    else:
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.png'
        pts = plots.scatter(points, xlabel, ylabel, title, exp.timeOut, filename, scaling=scaling)
        if request.args.has_key('imagemap'):
            mapdata = []
            for i in xrange(len(points)):
                mapdata.append(
                    {'x': pts[i][0],
                     'y': pts[i][1],
                     'url': url_for('frontend.instance_details',
                                    database=database,
                                    instance_id=points[i][2].idInstance),
                     'alt': points[i][2].name
                    }
                )
            return json.dumps({
                'data': mapdata
            })
        else:
            response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
        os.remove(filename)
        return response


def scatter_1solver_instance_vs_result_property(database, experiment_id):
    pass

@plot.route('/<database>/experiment/<int:experiment_id>/scatter-plot-2properties/')
@require_phase(phases=(5, 6, 7))
@require_login
def scatter_1solver_result_vs_result_property(database, experiment_id):
    """ description """
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    solver_config = int(request.args['solver_config'])
    run = request.args['run']
    scaling = request.args['scaling']
    solver_property1 = request.args['solver_property1']
    solver_property2 = request.args['solver_property2']

    instances = [db.session.query(db.Instance).filter_by(idInstance=int(id)).first() for id in request.args.getlist('instances')]

    if solver_property1 != 'cputime':
        solver_prop1 = db.session.query(db.SolverProperty).get(int(solver_property1))

    if solver_property2 != 'cputime':
        solver_prop2 = db.session.query(db.SolverProperty).get(int(solver_property2))

    solver_config = db.session.query(db.SolverConfiguration).get(solver_config) or abort(404)

    results = db.session.query(db.ExperimentResult)
    results.enable_eagerloads(True).options(joinedload(db.ExperimentResult.instance, db.ExperimentResult.solver_configuration))
    results = results.filter_by(experiment=exp, solver_configuration=solver_config)

    points = []
    if run == 'average':
        for instance in instances:
            s1_avg = numpy.average([j.get_property_value(solver_property1, db) for j in results.filter_by(instance=instance).all()])
            s2_avg = numpy.average([j.get_property_value(solver_property2, db) for j in results.filter_by(instance=instance).all()])
            points.append((s1_avg, s2_avg, instance))
    elif run == 'median':
        for instance in instances:
            x = numpy.median([j.get_property_value(solver_property1, db) for j in results.filter_by(instance=instance).all()])
            y = numpy.median([j.get_property_value(solver_property2, db) for j in results.filter_by(instance=instance).all()])
            points.append((x, y, instance))
    elif run == 'all':
        for instance in instances:
            xs = [j.get_property_value(solver_property1, db) for j in results.filter_by(instance=instance).all()]
            ys = [j.get_property_value(solver_property2, db) for j in results.filter_by(instance=instance).all()]
            points += zip(xs, ys, [instance] * len(xs))
    else:
        for instance in instances:
            res = results.filter_by(instance=instance, run=int(run)).first()
            points.append((
                r1.get_property_value(solver_property1, db),
                r2.get_property_value(solver_property2, db),
                instance
            ))

    if solver_property1 == 'cputime':
        xlabel = 'CPU Time'
    else:
        xlabel = solver_prop1.name

    if solver_property2 == 'cputime':
        ylabel = 'CPU Time'
    else:
        ylabel = solver_prop2.name

    title = str(solver_config)

    if request.args.has_key('csv'):
        csv_response = StringIO.StringIO()
        csv_writer = csv.writer(csv_response)
        csv_writer.writerow(['Instance', xlabel, ylabel])
        for x, y, i in points:
            csv_writer.writerow([str(i), x, y])
        csv_response.seek(0)

        headers = Headers()
        headers.add('Content-Type', 'text/csv')
        headers.add('Content-Disposition', 'attachment', filename="data.csv")
        return Response(response=csv_response.read(), headers=headers)

    elif request.args.has_key('pdf'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.pdf'
        plots.scatter(points, xlabel, ylabel, title, exp.timeOut, filename, format='pdf', scaling=scaling)
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename=str(solver_config) + '.pdf')
        response = Response(response=open(filename, 'rb').read(), mimetype='application/pdf', headers=headers)
        os.remove(filename)
        return response
    else:
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + '.png'
        pts = plots.scatter(points, xlabel, ylabel, title, exp.timeOut, filename, scaling=scaling)
        if request.args.has_key('imagemap'):
            mapdata = []
            for i in xrange(len(points)):
                mapdata.append(
                    {'x': pts[i][0],
                     'y': pts[i][1],
                     'url': url_for('frontend.instance_details',
                                    database=database,
                                    instance_id=points[i][2].idInstance),
                     'alt': points[i][2].name
                    }
                )
            return json.dumps({
                'data': mapdata
            })
        else:
            response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
        os.remove(filename)
        return response

@plot.route('/<database>/experiment/<int:experiment_id>/cactus-plot/')
@require_phase(phases=(5, 6, 7))
@require_login
def cactus_plot(database, experiment_id):
    """ Renders a cactus plot of the instances solved within a given "amount" of
        a result property of all solver configurations of the specified
        experiment
    """
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    results = db.session.query(db.ExperimentResult)
    results.enable_eagerloads(True).options(joinedload(db.ExperimentResult.solver_configuration))
    results = results.filter_by(experiment=exp)
    instances = [db.session.query(db.Instance).filter_by(idInstance=int(id)).first() for id in request.args.getlist('instances')]
    solver_property = request.args.get('solver_property') or 'cputime'
    if solver_property != 'cputime':
        solver_prop = db.session.query(db.SolverProperty).get(int(solver_property))

    solvers = []
    for sc in exp.solver_configurations:
        s = {'xs': [], 'ys': [], 'name': sc.get_name()}
        sc_res = results.filter_by(solver_configuration=sc, status=1)
        sc_res = sorted(sc_res, key=lambda r: r.get_property_value(solver_property, db))
        i = 1
        for r in sc_res:
            if r.instance in instances or instances == []:
                s['ys'].append(r.get_property_value(solver_property, db))
                s['xs'].append(i)
                i += 1
        solvers.append(s)

    max_x = max([max(s['xs'] or [0]) for s in solvers]) + 10
    max_y = max([max(s['ys'] or [0]) for s in solvers])

    if solver_property == 'cputime':
        ylabel = 'CPU Time (s)'
        title = 'Number of solved instances within a given amount of CPU time'
    else:
        ylabel = solver_prop.name
        title = 'Number of solved instances within a given amount of ' + solver_prop.name

    if request.args.has_key('pdf'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'cactus.pdf'
        plots.cactus(solvers, max_x, max_y, ylabel, title, filename, format='pdf')
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename='instances_solved.pdf')
        response = Response(response=open(filename, 'rb').read(), mimetype='application/pdf', headers=headers)
        os.remove(filename)
        return response
    else:
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'cactus.png'
        plots.cactus(solvers, max_x, max_y, ylabel, title, filename)
        response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
        os.remove(filename)
        return response


@plot.route('/<database>/experiment/<int:experiment_id>/rtd-comparison-plot/')
@require_phase(phases=(5, 6, 7))
@require_login
def rtd_comparison_plot(database, experiment_id):
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    instance = db.session.query(db.Instance).filter_by(idInstance=int(request.args['instance'])).first() or abort(404)
    s1 = db.session.query(db.SolverConfiguration).get(int(request.args['solver_config1'])) or abort(404)
    s2 = db.session.query(db.SolverConfiguration).get(int(request.args['solver_config2'])) or abort(404)

    results1 = [r.get_time() for r in db.session.query(db.ExperimentResult)
                                    .filter_by(experiment=exp,
                                               solver_configuration=s1,
                                               instance=instance).all()]
    results2 = [r.get_time() for r in db.session.query(db.ExperimentResult)
                                    .filter_by(experiment=exp,
                                               solver_configuration=s2,
                                               instance=instance).all()]

    if request.args.has_key('pdf'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'rtdcomp.png'
        plots.rtd_comparison(results1, results2, str(s1), str(s2), filename, format='pdf')
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename='rtdcomp.pdf')
        response = Response(response=open(filename, 'rb').read(), mimetype='application/pdf', headers=headers)
        os.remove(filename)
        return response
    else:
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'rtdcomp.png'
        plots.rtd_comparison(results1, results2, str(s1), str(s2), filename, 'png')
        response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
        os.remove(filename)
        return response


@plot.route('/<database>/experiment/<int:experiment_id>/rtds-plot/')
@require_phase(phases=(5, 6, 7))
@require_login
def rtds_plot(database, experiment_id):
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    instance = db.session.query(db.Instance).filter_by(idInstance=int(request.args['instance'])).first() or abort(404)
    solver_configs = [db.session.query(db.SolverConfiguration).get(int(id)) for id in request.args.getlist('sc')]

    results = []
    for sc in solver_configs:
        sc_results = db.session.query(db.ExperimentResult) \
                        .filter_by(experiment=exp, instance=instance,
                                   solver_configuration=sc).all()
        results.append((sc, [j.get_time() for j in sc_results]))

    if request.args.has_key('pdf'):
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'rtds.png'
        plots.rtds(results, filename, 'pdf')
        headers = Headers()
        headers.add('Content-Disposition', 'attachment', filename='rtds.pdf')
        response = Response(response=open(filename, 'rb').read(), mimetype='application/pdf', headers=headers)
        os.remove(filename)
        return response
    else:
        filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'rtds.png'
        plots.rtds(results, filename, 'png')
        response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
        os.remove(filename)
        return response

@plot.route('/<database>/experiment/<int:experiment_id>/box-plot/')
@require_phase(phases=(6, 7))
@require_login
def box_plot(database, experiment_id):
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    results = {}
    for sc in exp.solver_configurations:
        results[str(sc)] = [res.get_time() for res in db.session.query(db.ExperimentResult)
                                    .filter_by(experiment=exp,
                                               solver_configuration=sc).all()]

    filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'boxplot.png'
    plots.box_plot(results, filename, 'png')
    response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
    os.remove(filename)
    return response


@plot.route('/<database>/experiment/<int:experiment_id>/histogram/<int:solver_configuration_id>/<int:instance_id>/')
@require_phase(phases=(6, 7))
@require_login
def histogram(database, experiment_id, solver_configuration_id, instance_id):
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)
    sc = db.session.query(db.SolverConfiguration).get(solver_configuration_id) or abort(404)
    instance = db.session.query(db.Instance).filter_by(idInstance=instance_id).first() or abort(404)

    results = [r.get_time() for r in db.session.query(db.ExperimentResult)
                                    .filter_by(experiment=exp,
                                               solver_configuration=sc,
                                               instance=instance).all()]

    filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'hist.png'
    plots.hist(results, filename, 'png')
    response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
    os.remove(filename)
    return response


@plot.route('/<database>/experiment/<int:experiment_id>/ecdf/<int:solver_configuration_id>/<int:instance_id>/')
@require_phase(phases=(6, 7))
@require_login
def ecdf(database, experiment_id, solver_configuration_id, instance_id):
    db = models.get_database(database) or abort(404)
    exp = db.session.query(db.Experiment).get(experiment_id) or abort(404)
    sc = db.session.query(db.SolverConfiguration).get(solver_configuration_id) or abort(404)
    instance = db.session.query(db.Instance).filter_by(idInstance=instance_id).first() or abort(404)

    results = [r.get_time() for r in db.session.query(db.ExperimentResult)
                                    .filter_by(experiment=exp,
                                               solver_configuration=sc,
                                               instance=instance).all()]

    filename = os.path.join(config.TEMP_DIR, g.unique_id) + 'ecdf.png'
    plots.ecdf(results, filename, 'png')
    response = Response(response=open(filename, 'rb').read(), mimetype='image/png')
    os.remove(filename)
    return response