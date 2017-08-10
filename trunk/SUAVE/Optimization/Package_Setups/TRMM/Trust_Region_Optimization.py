# Trust_Region_Optimization.py
#
# Created:  Apr 2017, T. MacDonald
# Modified: Jun 2017, T. MacDonald

# ----------------------------------------------------------------------
#  Imports
# ----------------------------------------------------------------------

import numpy as np
import SUAVE
try:
    import pyOpt
except:
    pass
from SUAVE.Core import Data
from SUAVE.Optimization import helper_functions as help_fun
import os
import sys

# ----------------------------------------------------------------------
#  Trust Region Optimization Class
# ----------------------------------------------------------------------

class Trust_Region_Optimization(Data):
        
    def __defaults__(self):
        
        self.tag                                = 'TR_Opt'
        self.trust_region_max_iterations        = 30
        self.optimizer_max_iterations           = 30
        self.convergence_tolerance              = 1E-6
        self.optimizer_convergence_tolerance    = 1E-6  # used in SNOPT
        self.optimizer_constraint_tolerance     = 1E-6  # used in SNOPT
        self.difference_interval                = 1E-6 
        self.optimizer_function_precision       = 1E-12 # used in SNOPT
        self.trust_region_function_precision    = 1E-12
        self.optimizer_verify_level             = 0
        self.fidelity_levels                    = 2     # only two are currently supported
        self.evaluation_order                   = [1,2] # currently this order is necessary for proper functionality   
        self.optimizer                          = 'SNOPT'
        
    def optimize(self,problem,print_output=False):
        if print_output == False:
            devnull = open(os.devnull,'w')
            sys.stdout = devnull
            
        # History writing
        f_out = open('TRM_hist.txt','w')
        import datetime
        f_out.write(str(datetime.datetime.now())+'\n')       
        
        inp = problem.optimization_problem.inputs
        obj = problem.optimization_problem.objective
        con = problem.optimization_problem.constraints 
        tr  = problem.trust_region
        
        # Set inputs
        nam = inp[:,0] # names
        ini = inp[:,1] # initials
        bnd = inp[:,2] # x bounds
        scl = inp[:,3] # x scale
        typ = inp[:,4] # type
    
        (x,scaled_constraints,x_low_bound,x_up_bound,con_up_edge,con_low_edge,name) = self.scale_vals(inp, con, ini, bnd, scl)
        
        # ---------------------------
        # Trust region specific code
        # ---------------------------
        
        iterations = 0
        max_iterations = self.trust_region_max_iterations
        x = np.array(x,dtype='float')
        tr.center = x
        tr_center = x # trust region center
        x_initial = x*1.      
        
        while iterations < max_iterations:
            iterations += 1
            
            # History writing
            f_out.write('Iteration ----- ' + str(iterations) + '\n')
            f_out.write('x_center: ' + str(x.tolist()) + '\n')
            f_out.write('tr size  : ' + str(tr.size) + '\n')   
            
            f    = [None]*self.fidelity_levels
            df   = [None]*self.fidelity_levels
            g    = [None]*self.fidelity_levels
            dg   = [None]*self.fidelity_levels            
            
            for level in self.evaluation_order:
                problem.fidelity_level = level
                res = self.evaluate_model(problem,x,scaled_constraints)
                f[level-1]  = res[0]    # objective value
                df[level-1] = res[1]    # objective derivate vector
                g[level-1]  = res[2]    # constraints vector
                dg[level-1] = res[3]    # constraints jacobian
                # History writing
                f_out.write('Level    : ' + str(level) + '\n')
                f_out.write('f        : ' + str(res[0][0]) + '\n')
                f_out.write('df       : ' + str(res[1].tolist()) + '\n')
            # assumes high fidelity is last
            f_center = f[-1][0]
                
            # Calculate correction
            corrections = self.calculate_correction(f,df,g,dg,tr)
            
            # Calculate constraint violation
            g_violation_hi_center = self.calculate_constraint_violation(g[-1],con_low_edge,con_up_edge)
            
            # Subproblem
            tr_size = tr.size
            tr.lower_bound = np.max(np.vstack([x_low_bound,x-tr_size]),axis=0)
            tr.upper_bound = np.min(np.vstack([x_up_bound,x+tr_size]),axis=0)      
            
            # Set to base fidelity level for optimizing the corrected model
            problem.fidelity_level = 1
            
            if self.optimizer == 'SNOPT':
                opt_prob = pyOpt.Optimization('SUAVE',self.evaluate_corrected_model, corrections=corrections,tr=tr)
                
                for ii in xrange(len(obj)):
                    opt_prob.addObj('f',f_center) 
                for ii in xrange(0,len(inp)):
                    vartype = 'c'
                    opt_prob.addVar(nam[ii],vartype,lower=tr.lower_bound[ii],upper=tr.upper_bound[ii],value=x[ii])    
                for ii in xrange(0,len(con)):
                    if con[ii][1]=='<':
                        opt_prob.addCon(name[ii], type='i', upper=con_up_edge[ii])  
                    elif con[ii][1]=='>':
                        opt_prob.addCon(name[ii], type='i', lower=con_low_edge[ii],upper=np.inf)
                    elif con[ii][1]=='=':
                        opt_prob.addCon(name[ii], type='e', equal=con_up_edge[ii])      
                        
                   
                opt = pyOpt.pySNOPT.SNOPT()       
                
                opt.setOption('Major iterations limit'     , self.optimizer_max_iterations)
                opt.setOption('Major optimality tolerance' , self.optimizer_convergence_tolerance)
                opt.setOption('Major feasibility tolerance', self.optimizer_constraint_tolerance)
                opt.setOption('Function precision'         , self.optimizer_function_precision)
                opt.setOption('Verify level'               , self.optimizer_verify_level)           
                
                outputs = opt(opt_prob, sens_type='FD',problem=problem,corrections=corrections,tr=tr)
                
                # output value of 13 indicates that the optimizer could not find an optimum
                if outputs[2]['value'][0] == 13:
                    feasible_flag = False
                else:
                    feasible_flag = True
                fOpt_corr = outputs[0][0]
                xOpt_corr = outputs[1]
                gOpt_corr = np.zeros([1,len(con)])[0]  
                for ii in xrange(len(con)):
                    gOpt_corr[ii] = opt_prob._solutions[0]._constraints[ii].value  

            else:
                raise ValueError('Selected optimizer not implemented')
            success_flag = feasible_flag            
        
            
            
            # Constraint minization ------------------------------------------------------------------------
            if feasible_flag == False:
                print 'Infeasible within trust region, attempting to minimize constraint'
                
                if self.optimizer == 'SNOPT':
                    opt_prob = pyOpt.Optimization('SUAVE',self.evaluate_constraints, corrections=corrections,tr=tr,
                                                  lb=con_low_edge,ub=con_up_edge)
                    for ii in xrange(len(obj)):
                        opt_prob.addObj('constraint violation',0.) 
                    for ii in xrange(0,len(inp)):
                        vartype = 'c'
                        opt_prob.addVar(nam[ii],vartype,lower=tr.lower_bound[ii],upper=tr.upper_bound[ii],value=x[ii])           
                    opt = pyOpt.pySNOPT.SNOPT()            
                    opt.setOption('Major iterations limit'     , self.optimizer_max_iterations)
                    opt.setOption('Major optimality tolerance' , self.optimizer_convergence_tolerance)
                    opt.setOption('Major feasibility tolerance', self.optimizer_constraint_tolerance)
                    opt.setOption('Function precision'         , self.optimizer_function_precision)
                    opt.setOption('Verify level'               , self.optimizer_verify_level)                 
                   
                    con_outputs = opt(opt_prob, sens_type='FD',problem=problem,corrections=corrections,tr=tr,
                                      lb=con_low_edge,ub=con_up_edge)
                    xOpt_corr = con_outputs[1]
                    new_outputs = self.evaluate_corrected_model(x, problem=problem,corrections=corrections,tr=tr)
        
                    fOpt_corr = new_outputs[0][0][0]
                    gOpt_corr = np.zeros([1,len(con)])[0]   
                    for ii in xrange(len(con)):
                        gOpt_corr[ii] = new_outputs[1][ii]
                else:
                    raise ValueError('Selected optimizer not implemented')
                
                # Constraint minization end ------------------------------------------------------------------------
                

            print 'fOpt_corr = ', fOpt_corr
            print 'xOpt_corr = ', xOpt_corr
            print 'gOpt_corr = ', gOpt_corr
            
            # Evaluate high-fidelity at optimum
            problem.fidelity_level = np.max(self.fidelity_levels)
            fOpt_hi, gOpt_hi = self.evaluate_model(problem,xOpt_corr,scaled_constraints,der_flag=False)
            fOpt_hi = fOpt_hi[0]
        
            g_violation_opt_corr = self.calculate_constraint_violation(gOpt_corr,con_low_edge,con_up_edge)
            g_violation_opt_hi = self.calculate_constraint_violation(gOpt_hi,con_low_edge,con_up_edge)
            
            # Calculate ratio
            rho = self.accuracy_ratio(f_center,fOpt_hi, fOpt_corr, g_violation_hi_center, g_violation_opt_hi, 
                                      g_violation_opt_corr,tr)  
            
            # Acceptance Test
            accepted = 0
            if( fOpt_hi < f_center ):
                print 'Trust region update accepted since objective value is lower\n'
                accepted = 1
            elif( g_violation_opt_hi < g_violation_hi_center ):
                print 'Trust region update accepted since nonlinear constraint violation is lower\n'
                accepted = 1
            else:
                print 'Trust region update rejected (filter)\n'        
            
            # Update Trust Region Size
            print tr
            tr_action = self.update_tr_size(rho,tr,accepted)  
                
            # Terminate if trust region too small
            if( tr.size < tr.minimum_size ):
                print 'Trust region too small'
                f_out.write('Trust region too small')
                f_out.close()
                if print_output == False:
                    sys.stdout = sys.__stdout__                  
                return (fOpt_corr,xOpt_corr,'Trust region too small')
            
            # Terminate if solution is infeasible, no change is detected, and trust region does not expand
            if( success_flag == False and tr_action < 3 and\
                np.sum(np.isclose(xOpt_corr,x,rtol=1e-15,atol=1e-14)) == len(x) ):
                print 'Solution infeasible, no improvement can be made'
                f_out.write('Solution infeasible, no improvement can be made')
                f_out.close()
                if print_output == False:
                    sys.stdout = sys.__stdout__                  
                return (fOpt_corr,xOpt_corr,'Solution infeasible')      
            
            # History writing
            f_out.write('x opt    : ' + str(xOpt_corr.tolist()) + '\n')
            f_out.write('low obj  : ' + str(fOpt_corr)          + '\n')
            f_out.write('hi  obj  : ' + str(fOpt_hi)            + '\n')
            
            # Convergence check
            if (accepted==1 and (np.abs(f_center-fOpt_hi) < self.convergence_tolerance)):
                print 'Hard convergence reached'
                f_out.write('Hard convergence reached')
                f_out.close()
                if print_output == False:
                    sys.stdout = sys.__stdout__                  
                return (fOpt_corr,xOpt_corr,'convergence reached')            
            
            # Update trust region center
            if accepted == 1:
                x = xOpt_corr*1.
                tr.center = x*1.             
            
            print 'Iteration number: ' + str(iterations)
            print 'x value: ' + str(x.tolist())
            print 'Objective value: ' + str(fOpt_hi)
        
        f_out.write('Max iteration limit reached')
        f_out.close()
        print 'Max iteration limit reached'
        if print_output == False:
            sys.stdout = sys.__stdout__          
        return (fOpt_corr,xOpt_corr,'Max iteration limit reached')
            
        
    def evaluate_model(self,problem,x,cons,der_flag=True):
        f  = problem.objective(x)
        g  = problem.all_constraints(x)
        
        if der_flag == False:
            return f,g
        
        # build derivatives
        fd_step = self.difference_interval
        df, dg  = problem.finite_difference(x,diff_interval=fd_step)
        
        return (f,df,g,dg)


    def evaluate_corrected_model(self,x,problem=None,corrections=None,tr=None):
        
        obj   = problem.objective(x)
        const = problem.all_constraints(x).tolist()
        fail  = np.array(np.isnan(obj.tolist()) or np.isnan(np.array(const).any())).astype(int)
        
        A, b = corrections
        x0   = tr.center
        
        obj   = obj + np.dot(A[0,:],(x-x0))+b[0]
        const = const + np.matmul(A[1:,:],(x-x0))+b[1:]
        const = const.tolist()
    
        print 'Inputs'
        print x
        print 'Obj'
        print obj
        print 'Con'
        print const
            
        return obj,const,fail
    
    
    def evaluate_constraints(self,x,problem=None,corrections=None,tr=None,lb=None,ub=None):

        obj      = problem.objective(x) # evaluate the problem
        const    = problem.all_constraints(x).tolist()
        fail     = np.array(np.isnan(obj.tolist()) or np.isnan(np.array(const).any())).astype(int)
        
        A, b = corrections
        x0   = tr.center
        
        const = const + np.matmul(A[1:,:],(x-x0))+b[1:]
        const = const.tolist()
        
        # get the objective that matters here
        obj_cons = self.calculate_constraint_violation(const,lb,ub)
        const    = None
        
        print 'Inputs'
        print x
        print 'Cons violation'
        print obj_cons         
            
        return obj_cons,const,fail    
        
        
    def calculate_constraint_violation(self,gval,lb,ub):
        gdiff = []
  
        for i in range(len(gval)):
            if len(lb) > 0:
                if( gval[i] < lb[i] ):
                    gdiff.append(lb[i] - gval[i])
            if len(ub) > 0:    
                if( gval[i] > ub[i] ):
                    gdiff.append(gval[i] - ub[i])
    
        return np.linalg.norm(gdiff) # 2-norm of violation  
    
    def calculate_correction(self,f,df,g,dg,tr):
        nr = 1 + g[0].size
        nc = df[0].size
            
        A = np.empty((nr,nc))
        b = np.empty(nr)
            
        # objective correction
        A[0,:] = df[1] - df[0]
        b[0] = f[1] - f[0]
            
        # constraint corrections
        A[1:,:] = dg[1] - dg[0]
        b[1:] = g[1] - g[0]
            
        corr = (A,b)
        
        return corr   
    
    
    def scale_vals(self,inp,con,ini,bnd,scl):
        
        # Pull out the constraints and scale them
        bnd_constraints = help_fun.scale_const_bnds(con)
        scaled_constraints = help_fun.scale_const_values(con,bnd_constraints)

        x            = ini/scl        
        x_low_bound  = []
        x_up_bound   = []
        edge         = []
        name         = []
        con_up_edge  = []
        con_low_edge = []
        
        for ii in xrange(0,len(inp)):
            x_low_bound.append(bnd[ii][0]/scl[ii])
            x_up_bound.append(bnd[ii][1]/scl[ii])

        for ii in xrange(0,len(con)):
            name.append(con[ii][0])
            edge.append(scaled_constraints[ii])
            if con[ii][1]=='<':
                con_up_edge.append(edge[ii])
                con_low_edge.append(-np.inf)
            elif con[ii][1]=='>':
                con_up_edge.append(np.inf)
                con_low_edge.append(edge[ii])
            elif con[ii][1]=='=':
                con_up_edge.append(edge[ii])
                con_low_edge.append(edge[ii])
            
        x_low_bound  = np.array(x_low_bound)
        x_up_bound   = np.array(x_up_bound)
        con_up_edge  = np.array(con_up_edge)         
        con_low_edge = np.array(con_low_edge)        
        
        return (x,scaled_constraints,x_low_bound,x_up_bound,con_up_edge,con_low_edge,name)
    
    
    def accuracy_ratio(self,f_center,f_hi,f_corr,g_viol_center,g_viol_hi,g_viol_corr,tr):
        
        # center value does not change since the corrected function already matches
        high_fidelity_center  = tr.evaluate_function(f_center,g_viol_center)
        high_fidelity_optimum = tr.evaluate_function(f_hi,g_viol_hi)
        low_fidelity_center   = tr.evaluate_function(f_center,g_viol_center)
        low_fidelity_optimum  = tr.evaluate_function(f_corr,g_viol_corr)
        if ( np.abs(low_fidelity_center-low_fidelity_optimum) < self.trust_region_function_precision):
            rho = 1.
        else:
            rho = (high_fidelity_center-high_fidelity_optimum)/(low_fidelity_center-low_fidelity_optimum) 
            
        return rho
    
    
    def update_tr_size(self,rho,tr,accepted):
        
        tr_size_previous = tr.size
        tr_action = 0 # 1: shrink, 2: no change, 3: expand
        if( not accepted ): # shrink trust region
            tr.size = tr.size*tr.contraction_factor
            tr_action = 1
            print 'Trust region shrunk from %f to %f\n\n' % (tr_size_previous,tr.size)        
        elif( rho < 0. ): # bad fit, shrink trust region
            tr.size = tr.size*tr.contraction_factor
            tr_action = 1
            print 'Trust region shrunk from %f to %f\n\n' % (tr_size_previous,tr.size)
        elif( rho <= tr.contract_threshold ): # okay fit, shrink trust region
            tr.size = tr.size*tr.contraction_factor
            tr_action = 1
            print 'Trust region shrunk from %f to %f\n\n' % (tr_size_previous,tr.size)
        elif( rho <= tr.expand_threshold ): # pretty good fit, retain trust region
            tr_action = 2
            print 'Trust region size remains the same at %f\n\n' % tr.size
        elif( rho <= 1.25 ): # excellent fit, expand trust region
            tr.size = tr.size*tr.expansion_factor
            tr_action = 3
            print 'Trust region expanded from %f to %f\n\n' % (tr_size_previous,tr.size)
        else: # rho > 1.25, okay-bad fit, but good for us, retain trust region
            tr_action = 2
            print 'Trust region size remains the same at %f\n\n' % tr.size        
            
        return tr_action